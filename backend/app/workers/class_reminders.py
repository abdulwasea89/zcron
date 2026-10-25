"""Notify assigned trainers shortly before their scheduled classes."""

from __future__ import annotations

from datetime import timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import BookingStatus, NotificationKind, Role
from app.core.security import now_utc
from app.models.class_session import ClassBooking, ClassSession
from app.models.organization import Organization
from app.models.user import User
from app.integrations.email import send_email_safe
from app.models.membership import OrganizationMember
from app.models.staff import Task
from app.realtime import events
from app.services.audit_service import record_audit
from app.services.notifications_service import create_notification


async def run_member_class_reminders(session: AsyncSession, *, org_id: str) -> dict:
    now = now_utc()
    org = await session.get(Organization, org_id)
    if org is None:
        return {"created": 0, "email_accepted": 0}
    try:
        zone = ZoneInfo(org.timezone or "UTC")
    except ZoneInfoNotFoundError:
        zone = ZoneInfo("UTC")
    rows = (await session.execute(
        select(ClassBooking, ClassSession, OrganizationMember, User)
        .join(ClassSession, ClassSession.id == ClassBooking.class_session_id)
        .join(OrganizationMember, OrganizationMember.id == ClassBooking.member_id)
        .join(User, User.id == OrganizationMember.user_id)
        .where(
            ClassBooking.organization_id == org_id, ClassSession.organization_id == org_id,
            OrganizationMember.organization_id == org_id, OrganizationMember.banned.is_(False),
            User.is_active.is_(True), ClassBooking.status == BookingStatus.BOOKED,
            ClassBooking.reminder_created_at.is_(None), ClassSession.cancelled.is_(False),
            ClassSession.category == "class", ClassSession.starts_at > now,
            ClassSession.starts_at <= now + timedelta(hours=1),
        ).order_by(ClassSession.starts_at).limit(500)
        .with_for_update(of=ClassBooking, skip_locked=True)
    )).all()
    accepted = 0
    for booking, class_session, member, user in rows:
        starts = class_session.starts_at
        if starts.tzinfo is None:
            starts = starts.replace(tzinfo=timezone.utc)
        body = f"Reminder: {class_session.title} at {org.name} starts {starts.astimezone(zone):%b %d at %H:%M %Z}."
        await create_notification(
            session, org_id=org_id, recipient_user_id=member.user_id,
            category=NotificationKind.SYSTEM, title="Your class starts soon", body=body,
            data={"class_session_id": class_session.id, "booking_id": booking.id},
        )
        booking.reminder_email_accepted = await send_email_safe(user.email, "Your class starts soon", body)
        booking.reminder_created_at = now
        session.add(booking)
        accepted += int(booking.reminder_email_accepted)
        await record_audit(
            session, action="class.member_reminded", organization_id=org_id,
            entity_type="class_booking", entity_id=booking.id,
            metadata={"email_accepted": booking.reminder_email_accepted},
        )
        await events.class_changed(org_id, class_session_id=class_session.id, action="member_reminded")
    return {"created": len(rows), "email_accepted": accepted}


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
        title = f"Class reminder: {class_session.title}"
        description = f"Your class starts at {class_session.starts_at:%H:%M} UTC."
        exists = await session.execute(
            select(Task.id).where(
                Task.organization_id == org_id,
                Task.assignee_member_id == trainer.id,
                Task.title == title,
                Task.deadline == class_session.starts_at,
            ).limit(1)
        )
        if exists.scalar_one_or_none() is not None:
            skipped += 1
            continue

        task = Task(
            organization_id=org_id,
            title=title,
            description=description,
            assignee_member_id=trainer.id,
            deadline=class_session.starts_at,
        )
        session.add(task)
        await session.flush()
        await record_audit(
            session,
            action="class.trainer_reminder_created",
            organization_id=org_id,
            entity_type="task",
            entity_id=task.id,
            metadata={"class_session_id": class_session.id},
        )
        await create_notification(
            session,
            org_id=org_id,
            recipient_user_id=trainer.user_id,
            category=NotificationKind.TASK,
            title="Class starts soon",
            body=description,
            data={**data, "task_id": task.id},
        )
        await events.task_changed(org_id, task_id=task.id, action="created")
        sent += 1
    return {"sent": sent, "skipped": skipped}
