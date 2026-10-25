"""Notify assigned trainers shortly before their scheduled classes."""

from __future__ import annotations

import json
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import NotificationKind, Role
from app.core.security import now_utc
from app.models.class_session import ClassSession
from app.models.membership import OrganizationMember
from app.models.notification import Notification
from app.services.notifications_service import create_notification


async def run_class_reminders(session: AsyncSession, *, org_id: str) -> dict:
    now = now_utc()
    upcoming = (
        await session.execute(
            select(ClassSession)
            .where(
                ClassSession.organization_id == org_id,
                ClassSession.category == "class",
                ClassSession.cancelled.is_(False),
                ClassSession.trainer_member_id.is_not(None),
                ClassSession.starts_at > now,
                ClassSession.starts_at <= now + timedelta(hours=1),
            )
            .order_by(ClassSession.starts_at)
            .limit(500)
            .with_for_update(skip_locked=True)
        )
    ).scalars().all()

    sent = skipped = 0
    for class_session in upcoming:
        trainer = await session.get(OrganizationMember, class_session.trainer_member_id)
        if (
            trainer is None
            or trainer.organization_id != org_id
            or trainer.role != Role.TRAINER
            or trainer.banned
        ):
            skipped += 1
            continue

        data = {"class_session_id": class_session.id, "reminder": "one_hour"}
        marker = json.dumps(data)
        exists = await session.execute(
            select(Notification.id).where(
                Notification.organization_id == org_id,
                Notification.recipient_user_id == trainer.user_id,
                Notification.data == marker,
            ).limit(1)
        )
        if exists.scalar_one_or_none() is not None:
            skipped += 1
            continue

        await create_notification(
            session,
            org_id=org_id,
            recipient_user_id=trainer.user_id,
            category=NotificationKind.TASK,
            title=f"Class starts soon: {class_session.title}",
            body=f"Your class starts at {class_session.starts_at:%H:%M} UTC.",
            data=data,
        )
        sent += 1
    return {"sent": sent, "skipped": skipped}
