"""Unused membership value, held as gym-specific credit rather than cash."""
from datetime import timedelta
from decimal import Decimal, ROUND_DOWN
from fastapi import HTTPException
from sqlalchemy import update
from sqlmodel import select
from app.core.constants import MemberStatus, PaymentStatus, PlanBillingType, PlanStatus, SubscriptionStatus
from app.core.security import now_utc
from app.models.member_credit import MemberCreditAccount, MemberCreditEntry
from app.models.membership import OrganizationMember
from app.models.payment import Payment
from app.models.plan import MembershipPlan
from app.models.subscription import Subscription
from app.services.plan_entitlements import subscription_terms


def minor(amount):
    return int((Decimal(str(amount)) * 100).quantize(Decimal('1'), rounding=ROUND_DOWN))


async def lock_member(session, org_id, member_id):
    member = (await session.execute(select(OrganizationMember).where(
        OrganizationMember.id == member_id, OrganizationMember.organization_id == org_id
    ).with_for_update())).scalar_one_or_none()
    if not member or member.banned:
        raise HTTPException(404, "Member not found.")
    return member


async def account(session, org_id, member_id, currency):
    row = (await session.execute(select(MemberCreditAccount).where(
        MemberCreditAccount.organization_id == org_id, MemberCreditAccount.member_id == member_id,
        MemberCreditAccount.currency == currency.upper()))).scalar_one_or_none()
    if row is None:
        row = MemberCreditAccount(organization_id=org_id, member_id=member_id, currency=currency.upper())
        session.add(row)
        await session.flush()
    return row


async def post(session, *, org_id, member_id, currency, amount, reference, description):
    await lock_member(session, org_id, member_id)
    row = await account(session, org_id, member_id, currency)
    existing = (await session.execute(select(MemberCreditEntry).where(MemberCreditEntry.reference == reference))).scalar_one_or_none()
    if existing:
        if existing.account_id != row.id or existing.amount_minor != amount:
            raise HTTPException(409, "Credit request does not match the earlier operation.")
        return
    result = await session.execute(update(MemberCreditAccount).where(
        MemberCreditAccount.id == row.id, MemberCreditAccount.balance_minor + amount >= 0
    ).values(balance_minor=MemberCreditAccount.balance_minor + amount))
    if result.rowcount != 1:
        raise HTTPException(409, "Not enough vault credit. Refresh your balance.")
    session.add(MemberCreditEntry(account_id=row.id, reference=reference, amount_minor=amount, description=description))
    await session.flush()


async def remaining_value(session, sub):
    now = now_utc()
    if not sub.current_period_end or sub.current_period_end <= now:
        return 0
    if sub.prepaid_value_minor is not None:
        start = sub.prepaid_value_at or sub.started_at
        fraction = min(1, max(0, (sub.current_period_end - now).total_seconds() / max(1, (sub.current_period_end - start).total_seconds())))
        return int(sub.prepaid_value_minor * fraction)
    # Legacy subscriptions: credit only payments proven to fund this subscription.
    rows = (await session.execute(select(Payment).where(
        Payment.subscription_id == sub.id, Payment.organization_id == sub.organization_id,
        Payment.member_id == sub.member_id,
        Payment.status.in_([PaymentStatus.SUCCEEDED, PaymentStatus.PARTIALLY_REFUNDED]),
    ))).scalars().all()
    total = 0
    for payment in rows:
        start = max(sub.started_at, payment.paid_at or sub.started_at)
        fraction = min(1, max(0, (sub.current_period_end - now).total_seconds() / max(1, (sub.current_period_end - start).total_seconds())))
        paid = max(0, minor(payment.amount - payment.joining_fee_amount - payment.refunded_amount) - payment.vault_credited_minor)
        total += int(paid * fraction)
    return total


async def credit_unused(session, sub, *, reference, description, limit_minor=None):
    await lock_member(session, sub.organization_id, sub.member_id)
    await session.refresh(sub)
    existing = (await session.execute(select(MemberCreditEntry).where(MemberCreditEntry.reference == reference))).scalar_one_or_none()
    if existing:
        return existing.amount_minor
    value = await remaining_value(session, sub)
    amount = min(value, limit_minor) if limit_minor is not None else value
    if amount <= 0:
        return 0
    # Reserve the cash source against later refunds. Credit-funded resumptions
    # have no new cash payment; their original reservation stays in place.
    payments = (await session.execute(select(Payment).where(
        Payment.subscription_id == sub.id, Payment.organization_id == sub.organization_id,
        Payment.member_id == sub.member_id,
        Payment.status.in_([PaymentStatus.SUCCEEDED, PaymentStatus.PARTIALLY_REFUNDED]),
    ).with_for_update())).scalars().all()
    reserve = amount
    for payment in payments:
        take = min(reserve, max(0, minor(payment.amount - payment.joining_fee_amount - payment.refunded_amount) - payment.vault_credited_minor))
        payment.vault_credited_minor += take
        reserve -= take
        session.add(payment)
    # Any unbacked remainder came from previously spent vault credit (for
    # example, a member resumed with wallet funds). Return that value to the
    # vault too; reserve only the portion that still has cash available for a
    # separate refund.
    await post(session, org_id=sub.organization_id, member_id=sub.member_id, currency=sub.currency,
               amount=amount, reference=reference, description=description)
    sub.prepaid_value_minor = value - amount
    sub.prepaid_value_at = now_utc()
    session.add(sub)
    return amount


async def summary(session, org_id, member_id):
    accounts = (await session.execute(select(MemberCreditAccount).where(
        MemberCreditAccount.organization_id == org_id, MemberCreditAccount.member_id == member_id
    ))).scalars().all()
    result = []
    for row in accounts:
        entries = (await session.execute(select(MemberCreditEntry).where(MemberCreditEntry.account_id == row.id)
                                        .order_by(MemberCreditEntry.created_at.desc()).limit(50))).scalars().all()
        result.append({"currency": row.currency, "available_credit": row.balance_minor,
                       "transactions": [{"id": e.id, "amount": e.amount_minor,
                                         "description": e.description, "created_at": e.created_at} for e in entries]})
    return result


async def resume(session, *, org_id, member_id, plan_id, key):
    member = await lock_member(session, org_id, member_id)
    active = (await session.execute(select(Subscription).where(
        Subscription.organization_id == org_id, Subscription.member_id == member_id,
        Subscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.GRACE, SubscriptionStatus.FROZEN])
    ))).scalars().first()
    if active:
        raise HTTPException(409, "You already have an active membership. Use a plan change instead.")
    plan = await session.get(MembershipPlan, plan_id)
    if not plan or plan.organization_id != org_id or plan.status != PlanStatus.PUBLISHED:
        raise HTTPException(404, "Published plan not found.")
    if plan.billing_type != PlanBillingType.RECURRING or plan.price <= 0 or plan.included_credits is not None:
        raise HTTPException(422, "Vault-funded time is available for recurring plans without visit limits.")
    row = await account(session, org_id, member_id, plan.currency)
    value = min(row.balance_minor, minor(plan.price))
    if value <= 0:
        raise HTTPException(409, "No credit is available in this plan's currency.")
    now = now_utc()
    end, _ = subscription_terms(plan, at=now)
    funded_seconds = int((end - now).total_seconds() * value / minor(plan.price))
    if funded_seconds < 1:
        raise HTTPException(409, "The available credit is too small to fund membership time.")
    await post(session, org_id=org_id, member_id=member_id, currency=plan.currency, amount=-value,
               reference=f"resume:{org_id}:{member_id}:{key}", description=f"Resume {plan.name}")
    sub = Subscription(organization_id=org_id, member_id=member_id, plan_id=plan.id,
                       status=SubscriptionStatus.ACTIVE, price_snapshot=plan.price, currency=plan.currency,
                       started_at=now, current_period_end=now + timedelta(seconds=funded_seconds),
                       prepaid_value_minor=value, prepaid_value_at=now)
    member.member_status = MemberStatus.ACTIVE
    session.add_all([sub, member])
    await session.flush()
    from app.services.family_service import sync_family_status
    await sync_family_status(session, org_id, member_id, MemberStatus.ACTIVE)
    return {"message": "Membership resumed using vault credit. No card payment was taken.",
            "credit_used": value, "currency": plan.currency, "current_period_end": sub.current_period_end.isoformat()}


async def cancel(session, *, org_id, member_id, timing, key):
    member = await lock_member(session, org_id, member_id)
    sub = (await session.execute(select(Subscription).where(
        Subscription.organization_id == org_id, Subscription.member_id == member_id,
        Subscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.GRACE]),
    ).order_by(Subscription.started_at.desc()).with_for_update())).scalars().first()
    if sub is None:
        raise HTTPException(409, "There is no active membership to cancel.")
    if timing == "period_end" and sub.current_period_end and sub.current_period_end > now_utc():
        sub.cancel_at_period_end = True
        sub.auto_renew = False
        session.add(sub)
        return {"message": "Cancellation is scheduled for the end of your paid period.", "credit_added": 0}
    amount = await credit_unused(session, sub, reference=f"member-cancel:{org_id}:{member_id}:{key}",
                                 description="Unused value after membership cancellation")
    sub.status = SubscriptionStatus.CANCELLED
    sub.cancelled_at = now_utc()
    sub.cancel_at_period_end = False
    sub.auto_renew = False
    member.member_status = MemberStatus.CANCELLED
    session.add_all([sub, member])
    from app.services.family_service import sync_family_status
    await sync_family_status(session, org_id, member_id, MemberStatus.CANCELLED)
    return {"message": "Membership cancelled. Remaining paid value is in your vault.", "credit_added": amount}
