"""Deliver due staff reminders for the lead follow-up sequence."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.constants import NotificationKind
from app.core.security import now_utc
from app.integrations.email import send_email_safe
from app.models.lead import Lead, LeadFollowUp
from app.services.notifications_service import create_notification, notify_org_owners

_EMAILS = {
    0: (
        "Thanks for your interest",
        "Hi {name},\n\nThanks for your interest in training with us. Reply to this email if you have questions or would like help choosing your next step.\n\nWe look forward to meeting you.",
    ),
    1: (
        "Can we help you get started?",
        "Hi {name},\n\nJust checking in to see if you have any questions about getting started. Reply to this email and our team will be happy to help.",
    ),
    3: (
        "Find a time that works for you",
        "Hi {name},\n\nIf you are still considering training with us, we can help you find a class or tour time that fits your schedule. Reply and tell us what works for you.",
    ),
    7: (
        "One last check-in",
        "Hi {name},\n\nThis is our last scheduled check-in. If you would like to visit or have questions, just reply to this email. Thanks for considering us.",
    ),
}


async def run_due_lead_followups(session: AsyncSession, *, org_id: str) -> dict:
    due_rows = (
        await session.execute(
            select(LeadFollowUp, Lead)
            .join(Lead, Lead.id == LeadFollowUp.lead_id)
            .where(
                LeadFollowUp.organization_id == org_id,
                LeadFollowUp.status == "scheduled",
                LeadFollowUp.due_at <= now_utc(),
            )
            .order_by(LeadFollowUp.due_at)
            .with_for_update(of=LeadFollowUp, skip_locked=True)
        )
    ).all()
    delivered = 0
    skipped = 0
    for followup, lead in due_rows:
        if lead.stage in {"joined", "lost"}:
            followup.status = "skipped"
            session.add(followup)
            skipped += 1
            continue
        if lead.email_followup_consent and lead.email:
            subject, template = _EMAILS[followup.day]
            followup.email_attempted_at = now_utc()
            followup.email_attempts += 1
            sent = await send_email_safe(
                lead.email, subject, template.format(name=lead.name.split()[0]),
            )
            followup.email_status = "sent" if sent else "failed"
            followup.email_sent_at = now_utc() if sent else None
        else:
            followup.email_status = "skipped"
        data = {"lead_id": lead.id, "followup_id": followup.id, "day": followup.day}
        title = f"Lead follow-up due: {lead.name}"
        if followup.email_status == "sent":
            body = f"The day {followup.day} follow-up email was sent. Review replies and record the outcome."
        elif followup.email_status == "failed":
            body = f"Day {followup.day} email could not be delivered. Contact the lead manually and record the outcome."
        else:
            body = f"Day {followup.day} follow-up is due. No email consent is recorded; use a permitted channel."
        if lead.created_by:
            await create_notification(
                session,
                org_id=org_id,
                recipient_user_id=lead.created_by,
                category=NotificationKind.TASK,
                title=title,
                body=body,
                data=data,
            )
        else:
            await notify_org_owners(
                session,
                org_id=org_id,
                category=NotificationKind.TASK,
                title=title,
                body=body,
                data=data,
            )
        followup.status = "due"
        session.add(followup)
        delivered += 1
    return {"due": delivered, "skipped": skipped}
