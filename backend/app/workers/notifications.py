"""Notification helpers / background fan-out (Sections 9.5, 11.1).

Thin async helpers that batch email + push so callers (and future Celery tasks)
have one place to send member/staff notifications. Email and push both degrade
to dev stubs (see integrations), so this is runnable with no providers.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.constants import MemberStatus, NotificationKind, SubscriptionStatus
from app.core.security import now_utc
from app.integrations.email import send_email_safe as send_email
from app.integrations.push import send_push
from app.models.membership import OrganizationMember
from app.models.membership_reminder import MembershipReminder
from app.models.plan import MembershipPlan
from app.models.subscription import Subscription
from app.models.user import User


async def notify_member(
    session: AsyncSession, *, member_id: str, title: str, body: str, push_token: str | None = None
) -> None:
    member = await session.get(OrganizationMember, member_id)
    if member is None:
        return
    user = await session.get(User, member.user_id)
    if user is not None:
        await send_email(user.email, title, body)
    await send_push(push_token, title, body)


async def send_grace_reminders(session: AsyncSession, *, org_id: str) -> int:
    """Send one reminder on each of the first three days after expiry."""

    subs = (
        await session.execute(
            select(Subscription).where(
                Subscription.organization_id == org_id,
                Subscription.status == SubscriptionStatus.GRACE,
                Subscription.current_period_end.is_not(None),
            )
        )
    ).scalars().all()
    sent = 0
    today = now_utc().date()
    for sub in subs:
        days_overdue = (today - sub.current_period_end.date()).days
        if days_overdue not in {1, 2, 3} or (sub.grace_until and now_utc() > sub.grace_until):
            continue
        stage = f"grace_{days_overdue}"
        if await _reminder_exists(session, sub, stage):
            continue
        await _record_reminder(session, sub, stage)
        title = "Membership payment due"
        body = f"Your membership expired {days_overdue} day(s) ago. Please contact your gym to renew."
        await notify_member(session, member_id=sub.member_id, title=title, body=body)
        member = await session.get(OrganizationMember, sub.member_id)
        if member is not None:
            from app.services.notifications_service import create_notification

            await create_notification(
                session, org_id=org_id, recipient_user_id=member.user_id,
                category=NotificationKind.MEMBERSHIP, title=title, body=body,
                data={"subscription_id": sub.id, "reminder_stage": stage},
            )
        sent += 1
    return sent


async def send_pre_expiry_reminders(session: AsyncSession, *, org_id: str) -> int:
    """Send idempotent renewal reminders 7, 3, and 1 day before period end."""

    now = now_utc()
    today = now.date()
    subs = (await session.execute(select(Subscription).where(
        Subscription.organization_id == org_id,
        Subscription.status == SubscriptionStatus.ACTIVE,
        Subscription.current_period_end.is_not(None),
        Subscription.current_period_end >= now,
    ))).scalars().all()
    sent = 0
    for sub in subs:
        days_left = (sub.current_period_end.date() - today).days
        if days_left not in {7, 3, 1}:
            continue
        stage = f"pre_expiry_{days_left}"
        if await _reminder_exists(session, sub, stage):
            continue
        await _record_reminder(session, sub, stage)
        date_label = sub.current_period_end.strftime("%b %d, %Y").replace(" 0", " ")
        title = "Membership renewal coming up"
        body = f"Your membership ends in {days_left} day(s) ({date_label}). Contact your gym to renew."
        await notify_member(session, member_id=sub.member_id, title=title, body=body)
        member = await session.get(OrganizationMember, sub.member_id)
        if member is None:
            continue
        from app.services.notifications_service import create_notification

        await create_notification(
            session, org_id=org_id, recipient_user_id=member.user_id,
            category=NotificationKind.MEMBERSHIP, title=title, body=body,
            data={"subscription_id": sub.id, "reminder_stage": stage},
        )
        sent += 1
    return sent


async def _reminder_exists(
    session: AsyncSession, sub: Subscription, stage: str,
) -> bool:
    return (await session.execute(select(MembershipReminder.id).where(
        MembershipReminder.subscription_id == sub.id,
        MembershipReminder.period_end == sub.current_period_end,
        MembershipReminder.stage == stage,
    ))).first() is not None


async def _record_reminder(session: AsyncSession, sub: Subscription, stage: str) -> None:
    session.add(MembershipReminder(
        organization_id=sub.organization_id,
        subscription_id=sub.id,
        period_end=sub.current_period_end,
        stage=stage,
    ))
    await session.flush()


async def expire_due_memberships(session: AsyncSession, *, org_id: str) -> int:
    """Move active/grace members past their period end into expired (Section 9.3)."""

    now = now_utc()
    subs = (
        await session.execute(
            select(Subscription).where(
                Subscription.organization_id == org_id,
                Subscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.GRACE]),
                Subscription.current_period_end != None,  # noqa: E711
            )
        )
    ).scalars()
    expired = 0
    for sub in subs:
        if sub.current_period_end and sub.current_period_end < now:
            if sub.status == SubscriptionStatus.GRACE and sub.grace_until and sub.grace_until > now:
                continue
            member = await session.get(OrganizationMember, sub.member_id)
            if sub.cancel_at_period_end:
                from app.services.member_vault_service import credit_unused
                await credit_unused(session, sub, reference=f"period-end-cancel:{sub.id}",
                                    description="Unused value after scheduled membership cancellation")
                sub.status = SubscriptionStatus.CANCELLED
                sub.cancelled_at = now
                sub.cancel_at_period_end = False
            elif sub.scheduled_plan_id:
                target = await session.get(MembershipPlan, sub.scheduled_plan_id)
                if target is not None and target.organization_id == org_id and target.status.value == "published":
                    sub.plan_id = target.id
                    sub.price_snapshot = target.price
                    sub.currency = target.currency
                    sub.started_at = now
                    from app.services.plan_entitlements import subscription_terms
                    sub.current_period_end, sub.classes_remaining = subscription_terms(target, at=now)
                    sub.credits_allowance = sub.classes_remaining
                    sub.prepaid_value_minor = None
                    sub.prepaid_value_at = None
                    sub.scheduled_plan_id = None
                    sub.scheduled_plan_at = None
                    session.add(sub)
                    continue
                sub.status = SubscriptionStatus.EXPIRED
            else:
                sub.status = SubscriptionStatus.EXPIRED
            session.add(sub)
            if member is not None and member.member_status in {MemberStatus.ACTIVE, MemberStatus.GRACE}:
                member.member_status = MemberStatus.CANCELLED if sub.status == SubscriptionStatus.CANCELLED else MemberStatus.EXPIRED
                session.add(member)
                from app.services.family_service import sync_family_status

                await sync_family_status(session, org_id, member.id, member.member_status)
            expired += 1
    return expired


async def unfreeze_due_memberships(session: AsyncSession, *, org_id: str) -> int:
    """Resume approved membership pauses when their requested end date arrives."""

    now = now_utc()
    subs = (await session.execute(select(Subscription).where(
        Subscription.organization_id == org_id,
        Subscription.status == SubscriptionStatus.FROZEN,
        Subscription.frozen_until.is_not(None),
        Subscription.frozen_until <= now,
    ))).scalars().all()
    member_ids = {sub.member_id for sub in subs}
    resumed = 0
    from app.services.members_service import _unfreeze_member

    for member_id in member_ids:
        member = await session.get(OrganizationMember, member_id)
        if member is None or member.organization_id != org_id or member.member_status != MemberStatus.FROZEN:
            continue
        member_subs = (await session.execute(select(Subscription).where(
            Subscription.organization_id == org_id,
            Subscription.member_id == member_id,
            Subscription.status == SubscriptionStatus.FROZEN,
        ))).scalars().all()
        # A member can have multiple entitlements. Resume them together only
        # when every frozen entitlement has reached its end date.
        if not member_subs or any(not sub.frozen_until or sub.frozen_until > now for sub in member_subs):
            continue
        until_values = [sub.frozen_until for sub in member_subs if sub.frozen_until]
        resume_at = min(until_values) if until_values else now
        await _unfreeze_member(session, member, resumed_at=resume_at)
        from app.services.family_service import sync_family_status

        await sync_family_status(session, org_id, member.id, member.member_status)
        from app.services.notifications_service import create_notification

        await create_notification(
            session, org_id=org_id, recipient_user_id=member.user_id,
            category=NotificationKind.MEMBERSHIP, title="Membership pause ended",
            body="Your membership pause has ended and your membership is active again.",
            data={"member_id": member.id},
        )
        resumed += 1
    return resumed
