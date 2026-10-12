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
    """Email/push members in grace (Section 9.5: reminders on days 1, 2, day-3 morning)."""

    subs = (
        await session.execute(
            select(Subscription).where(
                Subscription.organization_id == org_id,
                Subscription.status == SubscriptionStatus.GRACE,
            )
        )
    ).scalars()
    sent = 0
    for sub in subs:
        days_left = 0
        if sub.grace_until:
            days_left = max(0, (sub.grace_until - now_utc()).days)
        await notify_member(session, member_id=sub.member_id, title="Payment due",
                            body=f"Your membership payment is due. {days_left} day(s) left.")
        # In-app alert mirrors the email (Section 9.5).
        member = await session.get(OrganizationMember, sub.member_id)
        if member is not None:
            from app.services.notifications_service import create_notification

            await create_notification(
                session, org_id=org_id, recipient_user_id=member.user_id,
                category=NotificationKind.MEMBERSHIP, title="Payment due",
                body=f"Your membership payment is due. {days_left} day(s) left.",
                data={"subscription_id": sub.id},
            )
        sent += 1
    return sent


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
            sub.status = SubscriptionStatus.EXPIRED
            session.add(sub)
            member = await session.get(OrganizationMember, sub.member_id)
            if member is not None and member.member_status in {MemberStatus.ACTIVE, MemberStatus.GRACE}:
                member.member_status = MemberStatus.EXPIRED
                session.add(member)
                from app.services.family_service import sync_family_status

                await sync_family_status(session, org_id, member.id, MemberStatus.EXPIRED)
            expired += 1
    return expired
