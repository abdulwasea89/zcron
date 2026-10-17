"""Consent-based member renewals processed directly on each gym's Stripe account."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.constants import (
    MemberStatus, PaymentKind, PaymentMethod, PaymentStatus, SubscriptionStatus, TaxMode,
)
from app.core.security import now_utc
from app.integrations.stripe_connect import connect_stripe
from app.models.membership import OrganizationMember
from app.models.organization import Organization
from app.models.payment import Payment
from app.models.plan import MembershipPlan
from app.models.subscription import Subscription
from app.services.plan_entitlements import subscription_terms


def _renewal_amount_cents(sub: Subscription, plan: MembershipPlan) -> tuple[int, int]:
    price = (Decimal(str(sub.price_snapshot)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    discount = Decimal("0")
    if (sub.save_discount_percent > 0 and sub.save_discount_expires_at
            and sub.save_discount_expires_at > now_utc()):
        discount = (price * Decimal(str(sub.save_discount_percent)) / 100).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    subtotal = max(Decimal("0"), price - discount)
    tax = Decimal("0")
    if plan.tax_mode == TaxMode.ADDED:
        tax = (subtotal * Decimal(str(plan.tax_rate))).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    return int(subtotal + tax), int(tax)


def _mark_grace(sub: Subscription, member: OrganizationMember, *, attempt: int) -> None:
    now = now_utc()
    sub.status = SubscriptionStatus.GRACE
    sub.renewal_attempt_count = attempt
    sub.grace_until = sub.grace_until or now + timedelta(days=3)
    # Do not blindly retry an ambiguous off-session charge. The member can
    # replace/reauthorize the method in Account; that action starts a new cycle
    # attempt with a new consent generation and idempotency key.
    sub.next_renewal_attempt_at = None
    member.member_status = MemberStatus.GRACE


async def complete_recurring_renewal(session: AsyncSession, payment: Payment) -> bool:
    """Extend one membership term once, only after Stripe confirms settlement."""
    sub = await session.get(Subscription, payment.subscription_id) if payment.subscription_id else None
    if sub is None or not (payment.note or "").startswith("member_renewal:"):
        return False
    sub = (await session.execute(
        select(Subscription).where(Subscription.id == sub.id).with_for_update()
    )).scalar_one()
    # The period key in the payment note prevents a replay from extending a
    # later term twice after Stripe's at-least-once webhook delivery.
    cycle_key = sub.current_period_end.isoformat() if sub.current_period_end else ""
    if not payment.note.startswith(f"member_renewal:{sub.id}:{cycle_key}:"):
        return True
    org = await session.get(Organization, sub.organization_id)
    member = await session.get(OrganizationMember, sub.member_id)
    plan = await session.get(MembershipPlan, sub.plan_id)
    if not org or not member or not plan:
        return False
    next_end, credits = subscription_terms(plan, at=now_utc())
    sub.started_at = now_utc()
    sub.current_period_end = next_end
    sub.status = SubscriptionStatus.ACTIVE
    sub.grace_until = None
    sub.renewal_attempt_count = 0
    sub.next_renewal_attempt_at = None
    sub.classes_remaining = credits
    sub.credits_allowance = credits
    sub.prepaid_value_minor = max(0, int(round(payment.amount * 100)))
    sub.prepaid_value_at = now_utc()
    member.member_status = MemberStatus.ACTIVE
    session.add(sub)
    session.add(member)
    from app.services.family_service import sync_family_status
    await sync_family_status(session, org.id, member.id, MemberStatus.ACTIVE)
    return True


async def fail_recurring_renewal(session: AsyncSession, payment: Payment) -> bool:
    if not (payment.note or "").startswith("member_renewal:") or not payment.subscription_id:
        return False
    sub = await session.get(Subscription, payment.subscription_id)
    if sub is None:
        return False
    cycle_key = sub.current_period_end.isoformat() if sub.current_period_end else ""
    if (not sub.auto_renew or sub.cancel_at_period_end
            or sub.status not in {SubscriptionStatus.ACTIVE, SubscriptionStatus.GRACE}
            or not payment.note.startswith(f"member_renewal:{sub.id}:{cycle_key}:")):
        # Stripe can deliver an old failure after a later renewal has already
        # succeeded. Do not let that stale event put the current term into grace.
        return True
    member = await session.get(OrganizationMember, sub.member_id)
    if member is None:
        return False
    _mark_grace(sub, member, attempt=max(1, sub.renewal_attempt_count))
    session.add(sub)
    session.add(member)
    from app.services.family_service import sync_family_status
    await sync_family_status(session, sub.organization_id, member.id, MemberStatus.GRACE)
    return True


async def run_due_member_renewals(session: AsyncSession, *, org_id: str) -> dict:
    now = now_utc()
    subs = (await session.execute(select(Subscription).where(
        Subscription.organization_id == org_id,
        Subscription.auto_renew.is_(True),
        Subscription.cancel_at_period_end.is_(False),
        Subscription.scheduled_plan_id.is_(None),
        Subscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.GRACE]),
        Subscription.current_period_end.is_not(None),
        Subscription.current_period_end <= now,
        Subscription.renewal_attempt_count < 3,
        or_(
            (Subscription.renewal_attempt_count == 0) & Subscription.next_renewal_attempt_at.is_(None),
            Subscription.next_renewal_attempt_at <= now,
        ),
    ).with_for_update(skip_locked=True))).scalars().all()
    succeeded = pending = failed = skipped = 0
    for sub in subs:
        # The subscription lock serializes workers. Derive the payment key from
        # the term and attempt so retries never duplicate a prior charge.
        sub = (await session.execute(
            select(Subscription).where(Subscription.id == sub.id).with_for_update()
        )).scalar_one()
        member = await session.get(OrganizationMember, sub.member_id)
        org = await session.get(Organization, org_id)
        plan = await session.get(MembershipPlan, sub.plan_id)
        if not member or not org or not plan:
            skipped += 1
            continue
        if plan.billing_type.value != "recurring" or not plan.auto_renew:
            sub.auto_renew = False
            session.add(sub)
            skipped += 1
            continue
        if not org.stripe_connect_account_id or not member.stripe_customer_id or not member.stripe_default_payment_method_id or not member.recurring_consent_at:
            _mark_grace(sub, member, attempt=min(3, sub.renewal_attempt_count + 1))
            session.add(member)
            session.add(sub)
            from app.services.family_service import sync_family_status
            await sync_family_status(session, org_id, member.id, MemberStatus.GRACE)
            skipped += 1
            continue
        cycle_key = sub.current_period_end.isoformat()
        attempt = sub.renewal_attempt_count + 1
        # Distinguish payment-method replacements even when re-consented in
        # the same second.
        consent_generation = int(member.recurring_consent_at.timestamp() * 1_000_000)
        note = f"member_renewal:{sub.id}:{cycle_key}:{attempt}:{consent_generation}"
        previous = (await session.execute(select(Payment).where(
            Payment.organization_id == org_id, Payment.note == note,
        ))).scalars().first()
        if previous is not None:
            if previous.status == PaymentStatus.SUCCEEDED:
                await complete_recurring_renewal(session, previous)
                succeeded += 1
            else:
                skipped += 1
            continue
        amount, tax = _renewal_amount_cents(sub, plan)
        payment = Payment(
            organization_id=org_id, member_id=member.id, subscription_id=sub.id,
            plan_id=plan.id, kind=PaymentKind.MEMBER_FEE, method=PaymentMethod.CARD,
            status=PaymentStatus.PENDING, amount=amount / 100, plan_price_amount=sub.price_snapshot,
            tax_amount=tax / 100, currency=sub.currency, note=note,
            recurring_consent=True,
            idempotency_key=(
                f"renew-{sub.id}-{int(sub.current_period_end.timestamp())}-"
                f"{attempt}-{consent_generation}"
            ),
        )
        session.add(payment)
        await session.flush()
        if amount <= 0:
            payment.status = PaymentStatus.SUCCEEDED
            payment.paid_at = now
            await complete_recurring_renewal(session, payment)
            succeeded += 1
            continue
        try:
            result = await connect_stripe.charge_member_off_session(
                connected_account_id=org.stripe_connect_account_id or "",
                customer_id=member.stripe_customer_id,
                payment_method_id=member.stripe_default_payment_method_id,
                amount_cents=amount, currency=sub.currency.lower(),
                idempotency_key=payment.idempotency_key,
                description=f"{org.name} membership renewal — {plan.name}",
                metadata={"purpose": "member_renewal", "payment_id": payment.id,
                          "subscription_id": sub.id, "member_id": member.id,
                          "organization_id": org_id},
            )
        except Exception:
            # No error details from Stripe are exposed in the member account.
            payment.status = PaymentStatus.FAILED
            _mark_grace(sub, member, attempt=attempt)
            from app.services.family_service import sync_family_status
            await sync_family_status(session, org_id, member.id, MemberStatus.GRACE)
            failed += 1
        else:
            payment.stripe_payment_intent_id = result.id
            payment.stripe_charge_id = result.charge_id
            payment.stripe_payment_method_id = result.payment_method_id or member.stripe_default_payment_method_id
            if result.status == "succeeded":
                payment.status = PaymentStatus.SUCCEEDED
                payment.paid_at = now_utc()
                try:
                    detail = await connect_stripe.inspect_member_intent(
                        connected_account_id=org.stripe_connect_account_id,
                        intent_id=result.id,
                    )
                    if detail is not None:
                        payment.stripe_payment_method_type = detail.payment_method_type
                        payment.stripe_charge_id = detail.charge_id or payment.stripe_charge_id
                except Exception:
                    # The successful charge is authoritative; detail is optional.
                    pass
                await complete_recurring_renewal(session, payment)
                succeeded += 1
            elif result.status == "processing":
                sub.status = SubscriptionStatus.GRACE
                sub.renewal_attempt_count = attempt
                sub.grace_until = sub.grace_until or now + timedelta(days=3)
                sub.next_renewal_attempt_at = None  # wait for the authoritative Stripe webhook
                member.member_status = MemberStatus.GRACE
                pending += 1
            else:
                payment.status = PaymentStatus.FAILED
                _mark_grace(sub, member, attempt=attempt)
                from app.services.family_service import sync_family_status
                await sync_family_status(session, org_id, member.id, MemberStatus.GRACE)
                failed += 1
        session.add(payment)
        session.add(sub)
        session.add(member)
    return {"due": len(subs), "succeeded": succeeded, "processing": pending,
            "failed": failed, "skipped": skipped}
