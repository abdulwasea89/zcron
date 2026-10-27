"""Send a consented lead follow-up text through the connected inbox provider."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.constants import Channel, Role
from app.models.lead import Lead
from app.models.membership import OrganizationMember
from app.models.organization import Organization
from app.services import inbox_service
from app.services.inbox_channels_service import get_credentials

SMS_TEMPLATES = {
    0: "Hi {name}, thanks for your interest in training with us. Reply here with any questions.",
    1: "Hi {name}, checking in to see if you have questions about getting started.",
    3: "Hi {name}, we can help you find a class or tour time. Reply here to get started.",
    7: "Hi {name}, one last check-in. Reply here if you would like to visit or have questions.",
}


def configured_sms_template(day: int, templates: dict | None = None) -> str:
    return (templates or {}).get(str(day), {}).get("sms_body") or SMS_TEMPLATES[day]


async def send_lead_followup_sms(session: AsyncSession, *, lead: Lead, day: int) -> str:
    if not lead.phone or not lead.sms_followup_consent:
        return "skipped"
    credentials = await get_credentials(session, lead.organization_id, Channel.SMS.value)
    if not credentials:
        return "failed"
    actor_id = lead.created_by or (await session.execute(select(OrganizationMember.user_id).where(
        OrganizationMember.organization_id == lead.organization_id,
        OrganizationMember.role == Role.OWNER,
        OrganizationMember.banned.is_(False),
    ).limit(1))).scalar_one_or_none()
    if not actor_id:
        return "failed"
    conversation = await inbox_service.find_or_create(
        session, org_id=lead.organization_id, channel=Channel.SMS,
        handle=lead.phone, contact_name=lead.name,
    )
    org = await session.get(Organization, lead.organization_id)
    template = configured_sms_template(day, org.lead_followup_templates if org else None)
    text = f"{template.replace('{name}', lead.name.split()[0])} Reply STOP to opt out."
    thread = await inbox_service.reply(
        session, org_id=lead.organization_id, user_id=actor_id,
        conversation_id=conversation.id, body=text,
        idempotency_key=f"lead-followup:{lead.id}:{day}",
    )
    message = next((item for item in reversed(thread["messages"]) if item["direction"] == "outbound"), None)
    return "sent" if message and message.get("delivery_status") in {"sent", "delivered"} else "failed"
