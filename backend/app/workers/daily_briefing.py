"""Deliver one daily owner briefing through the existing in-app feed."""

from __future__ import annotations

import json
from datetime import timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.agent import workflows
from app.core.constants import NotificationKind, Role
from app.core.security import now_utc
from app.integrations.email import send_email_safe
from app.models.membership import OrganizationMember
from app.models.notification import Notification
from app.models.organization import Organization
from app.models.user import User
from app.services.notifications_service import create_notification


async def run_daily_owner_brief(session: AsyncSession, *, org_id: str) -> dict:
    org = await session.get(Organization, org_id)
    if org is None:
        return {"sent": 0, "reason": "organization_not_found"}

    current = now_utc()
    try:
        local_now = current.astimezone(ZoneInfo(org.timezone or "UTC"))
    except (ZoneInfoNotFoundError, ValueError):
        local_now = current.astimezone(timezone.utc)
    if local_now.hour != 9:
        return {"sent": 0, "reason": "outside_delivery_hour"}

    admins = (await session.execute(select(OrganizationMember).where(
        OrganizationMember.organization_id == org_id,
        OrganizationMember.role.in_([Role.OWNER, Role.MANAGER]),
        OrganizationMember.banned.is_(False),
    ))).scalars().all()
    if not admins:
        return {"sent": 0, "reason": "no_recipients"}

    key = {"briefing_date": local_now.date().isoformat()}
    already_sent = set((await session.execute(select(
        Notification.recipient_user_id,
    ).where(
        Notification.organization_id == org_id,
        Notification.title == "Daily owner brief",
        Notification.data == json.dumps(key),
        Notification.recipient_user_id.in_([admin.user_id for admin in admins]),
    ))).scalars().all())
    recipients = [admin.user_id for admin in admins if admin.user_id not in already_sent]
    if not recipients:
        return {"sent": 0, "reason": "already_sent"}

    body = await workflows.weekly_briefing(session, org_id=org_id, role=Role.OWNER)
    for user_id in recipients:
        await create_notification(
            session, org_id=org_id, recipient_user_id=user_id,
            category=NotificationKind.SYSTEM, title="Daily owner brief",
            body=body, data=key,
        )
        member = next((admin for admin in admins if admin.user_id == user_id), None)
        user = await session.get(User, user_id)
        if member and member.daily_brief_email and user and user.email_verified:
            await send_email_safe(user.email, f"{org.name}: daily owner brief", body)
    return {"sent": len(recipients), "briefing_date": key["briefing_date"]}
