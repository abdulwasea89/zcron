"""Consent-based member renewals processed directly on each gym's Stripe account."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.constants import (
    MemberStatus, NotificationKind, PaymentKind, PaymentMethod, PaymentStatus,
    SubscriptionStatus, TaxMode,
)
from app.core.config import settings
from app.core.security import now_utc
from app.integrations.stripe_connect import connect_stripe
from app.models.membership import OrganizationMember
from app.models.organization import Organization
from app.models.payment import Payment
from app.models.membership_reminder import MembershipReminder
from app.models.plan import MembershipPlan
from app.models.subscription import Subscription
from app.models.user import User
from app.services.plan_entitlements import subscription_terms


MAX_RENEWAL_ATTEMPTS = 3


def _field(value, key: str):
    if isinstance(value, dict):
        return value.get(key)
    return getattr(value, key, None)


def _stripe_failure_details(source) -> dict:
    """Read safe retry signals and an intent reference from Stripe errors/events."""
    payload = source
    json_body = _field(source, "json_body")
    if json_body:
        payload = json_body
    error = _field(payload, "error") or payload
    intent = _field(error, "payment_intent") or _field(payload, "payment_intent")
    last_error = _field(payload, "last_payment_error") or _field(intent, "last_payment_error") or error
    charge = _field(intent, "latest_charge") or _field(payload, "latest_charge")
    outcome = _field(charge, "outcome")
    code = _field(last_error, "code") or _field(error, "code")
    decline = _field(last_error, "decline_code") or _field(error, "decline_code")
    advice = (_field(last_error, "advice_code") or _field(outcome, "advice_code")
              or _field(error, "advice_code"))
    retryable = advice == "try_again_later" or (
        advice != "do_not_try_again"
        and decline in {"insufficient_funds", "processing_error", "issuer_not_available"}
    )
    return {
        "retryable": retryable,
        "code": code,
        "decline_code": decline,
        "payment_intent_id": intent if isinstance(intent, str) else _field(intent, "id"),
        "charge_id": _field(charge, "id") if not isinstance(charge, str) else charge,
    }


def _retry_delay(attempt: int, decline_code: str | None) -> timedelta:
    # Insufficient-funds retries leave a day for the member to add funds.
    # Processor/issuer errors use a shorter first retry and a longer second wait.
    if decline_code == "insufficient_funds":
        return timedelta(days=1)
    return timedelta(hours=6 if attempt == 1 else 18)


def _schedule_retry(sub: Subscription, member: OrganizationMember, *, attempt: int, retryable: bool,
                    decline_code: str | None) -> None:
    _mark_grace(sub, member, attempt=attempt)
    if retryable and attempt < MAX_RENEWAL_ATTEMPTS:
        sub.next_renewal_attempt_at = now_utc() + _retry_delay(attempt, decline_code)


async def _notify_member_payment_failure(session: AsyncSession, sub: Subscription,
                                         member: OrganizationMember) -> None:
    """Send the first dunning notice once per billing period."""
    stage = "grace_0"
    if (await session.execute(select(MembershipReminder.id).where(
        MembershipReminder.subscription_id == sub.id,
        MembershipReminder.period_end == sub.current_period_end,
        MembershipReminder.stage == stage,
    ))).first() is not None:
        return
    session.add(MembershipReminder(
        organization_id=sub.organization_id, subscription_id=sub.id,
        period_end=sub.current_period_end, stage=stage,
    ))
    await session.flush()
    user = await session.get(User, member.user_id)
    if user is None:
        return
    account_url = f"{settings.frontend_url.rstrip('/')}/app/account"
    retry_text = (
        f"We will retry on {sub.next_renewal_attempt_at.strftime('%b %d at %H:%M UTC')}. "
        if sub.next_renewal_attempt_at else "Automatic retries are unavailable for this decline. "
    )
    title = "Membership renewal payment failed"
    body = (
        f"Your membership renewal needs attention. {retry_text}You can update or reauthorize "
        f"your payment method in your account: {account_url}"
    )
    from app.integrations.email import send_email_safe
    from app.integrations.push import send_push
    from app.services.notifications_service import create_notification

    await send_email_safe(user.email, title, body)
    await send_push(None, title, "Open your account to review the renewal payment.")
    await create_notification(
        session, org_id=sub.organization_id, recipient_user_id=user.id,
        category=NotificationKind.MEMBERSHIP, title=title, body=body,
        data={"subscription_id": sub.id, "retry_at": sub.next_renewal_attempt_at},
    )


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
    # The caller schedules a retry only when Stripe explicitly identifies a
    # retryable decline. Ambiguous failures remain stopped to avoid duplicates.
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


async def fail_recurring_renewal(session: AsyncSession, payment: Payment, *, failure=None) -> bool:
    if not (payment.note or "").startswith("member_renewal:") or not payment.subscription_id:
        return False
    sub = (await session.execute(select(Subscription).where(
        Subscription.id == payment.subscription_id,
    ).with_for_update())).scalar_one_or_none()
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
    # A duplicate event must preserve its already scheduled next retry.
    if sub.next_renewal_attempt_at is None:
        details = _stripe_failure_details(failure or {})
        _schedule_retry(
            sub, member, attempt=max(1, sub.renewal_attempt_count),
            retryable=details["retryable"], decline_code=details["decline_code"],
        )
    else:
        retry_at = sub.next_renewal_attempt_at
        _mark_grace(sub, member, attempt=max(1, sub.renewal_attempt_count))
        sub.next_renewal_attempt_at = retry_at
    await _notify_member_payment_failure(session, sub, member)
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
            await _notify_member_payment_failure(session, sub, member)
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
        except Exception as exc:
            details = _stripe_failure_details(exc)
            payment.status = PaymentStatus.FAILED
            payment.stripe_payment_intent_id = details["payment_intent_id"]
            payment.stripe_charge_id = details["charge_id"]
            payment.stripe_failure_code = details["code"]
            payment.stripe_failure_decline_code = details["decline_code"]
            _schedule_retry(
                sub, member, attempt=attempt, retryable=details["retryable"],
                decline_code=details["decline_code"],
            )
            await _notify_member_payment_failure(session, sub, member)
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
                payment.stripe_failure_code = "payment_not_succeeded"
                _schedule_retry(sub, member, attempt=attempt, retryable=False,
                                decline_code=None)
                await _notify_member_payment_failure(session, sub, member)
                from app.services.family_service import sync_family_status
                await sync_family_status(session, org_id, member.id, MemberStatus.GRACE)
                failed += 1
        session.add(payment)
        session.add(sub)
        session.add(member)
    return {"due": len(subs), "succeeded": succeeded, "processing": pending,
            "failed": failed, "skipped": skipped}
