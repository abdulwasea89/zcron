"""Segmented campaigns by channel (#39).

A campaign is an owner-authored message aimed at a resolved segment of members
and pushed over a chosen channel (or channels). It reuses the same attendance
stream the retention stack reads, so segments like "monthly-plan holders who
haven't visited in 15 days" fall out of data we already row.

* **Audience:** status filter (defaults to active), optional plan, optional
  minimum absence in days. Resolved into concrete member rows at send time —
  the segment is computed, not stored, so it is always current.
* **Channels:** in-app notification and/or email. Each channel requires explicit
  member marketing consent; email additionally requires a verified address.
* **Idempotency:** a unique (campaign, member) delivery pair means resuming a
  partially-sent campaign — whether re-run manually or by the scheduled worker —
  never double-sends (Security Rule #2).
"""

from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.constants import (
    Channel,
    CampaignChannel,
    CampaignDeliveryStatus,
    CampaignStatus,
    MemberStatus,
    NotificationKind,
    Role,
)
from app.core.security import now_utc
from app.integrations.email import send_email_safe as send_email
from app.integrations.inbox_channels import deliver as deliver_inbox_message
from app.models.attendance import Attendance
from app.models.campaign import Campaign, CampaignDelivery
from app.models.membership import OrganizationMember
from app.models.subscription import Subscription
from app.models.user import User
from app.services.audit_service import record_audit

_ACTIVE_LIKE = [MemberStatus.ACTIVE, MemberStatus.GRACE, MemberStatus.FROZEN]
DEFAULT_SEND_LIMIT = 200


# ------------------------------------------------------------------- helpers
async def _get_campaign(session: AsyncSession, org_id: str, campaign_id: str) -> Campaign:
    campaign = await session.get(Campaign, campaign_id)
    if campaign is None or campaign.organization_id != org_id:
        raise HTTPException(status_code=404, detail="Campaign not found in this organization.")
    return campaign


def _status_set(raw: str | None) -> list[MemberStatus]:
    if not raw:
        return list(_ACTIVE_LIKE)
    return [MemberStatus(s.strip()) for s in raw.split(",") if s.strip()]


async def _last_visits(
    session: AsyncSession, *, org_id: str, member_ids: list[str]
) -> dict[str, datetime]:
    if not member_ids:
        return {}
    rows = (
        await session.execute(
            select(Attendance.member_id, func.max(Attendance.checked_in_at))
            .where(
                Attendance.organization_id == org_id,
                Attendance.member_id.in_(member_ids),  # type: ignore[attr-defined]
            )
            .group_by(Attendance.member_id)
        )
    ).all()
    return {mid: last for mid, last in rows}


async def _resolve_segment(
    session: AsyncSession, org_id: str, campaign: Campaign
) -> list[OrganizationMember]:
    """Resolve the campaign's audience criteria into concrete member rows."""

    stmt = select(OrganizationMember).where(
        OrganizationMember.organization_id == org_id,
        OrganizationMember.role == Role.MEMBER,
        OrganizationMember.member_status.in_(  # type: ignore[attr-defined]
            list(_status_set(campaign.member_status))
        ),
    )
    candidates = list((await session.execute(stmt)).scalars().all())
    if not candidates:
        return []

    wants_sms = campaign.channel == CampaignChannel.SMS
    wants_email = campaign.channel in {CampaignChannel.EMAIL, CampaignChannel.BOTH}
    wants_in_app = campaign.channel in {CampaignChannel.IN_APP, CampaignChannel.BOTH}
    candidates = [
        member for member in candidates
        if (wants_sms and member.marketing_sms_consent and member.phone and member.phone.strip())
        or (wants_email and member.marketing_email_consent)
        or (wants_in_app and member.marketing_in_app_consent)
    ]
    if not candidates:
        return []

    ids = [m.id for m in candidates]
    if campaign.plan_id is not None:
        plan_ids = {
            s.member_id
            for s in (
                await session.execute(
                    select(Subscription).where(
                        Subscription.organization_id == org_id,
                        Subscription.plan_id == campaign.plan_id,
                        Subscription.status.in_(  # type: ignore[attr-defined]
                            list(_ACTIVE_LIKE),
                        ),
                    )
                )
            )
            .scalars()
            .all()
        }
        candidates = [m for m in candidates if m.id in plan_ids]

    if campaign.min_days_since_last_visit:
        last_visits = await _last_visits(session, org_id=org_id, member_ids=ids)
        now = now_utc()
        candidates = [
            m
            for m in candidates
            if last_visits.get(m.id) is None
            or (now - last_visits[m.id]).days >= campaign.min_days_since_last_visit
        ]

    return candidates


async def _name(member: OrganizationMember, user: User | None) -> str:
    return (
        member.display_name
        or (user.full_name if user else None)
        or (user.email if user else None)
        or "there"
    )


# -------------------------------------------------------------------- admin CRUD
async def create_campaign(
    session: AsyncSession,
    *,
    org_id: str,
    actor_user_id: str | None,
    title: str,
    subject: str,
    body: str,
    channel: CampaignChannel = CampaignChannel.IN_APP,
    member_status: str | None = None,
    plan_id: str | None = None,
    min_days_since_last_visit: int | None = None,
    scheduled_at: datetime | None = None,
    send_limit: int = DEFAULT_SEND_LIMIT,
) -> Campaign:
    if not title.strip():
        raise HTTPException(status_code=422, detail="title is required.")
    if not subject.strip() or not body.strip():
        raise HTTPException(status_code=422, detail="subject and body are required.")
    if min_days_since_last_visit is not None and min_days_since_last_visit < 1:
        raise HTTPException(status_code=422, detail="min_days_since_last_visit must be >= 1.")
    if send_limit < 1:
        raise HTTPException(status_code=422, detail="send_limit must be >= 1.")
    if channel == CampaignChannel.SMS and send_limit > DEFAULT_SEND_LIMIT:
        raise HTTPException(status_code=422, detail="SMS campaigns are limited to 200 recipients per send.")

    campaign = Campaign(
        organization_id=org_id,
        title=title.strip(),
        subject=subject.strip(),
        body=body.strip(),
        channel=channel,
        member_status=member_status,
        plan_id=plan_id,
        min_days_since_last_visit=min_days_since_last_visit,
        scheduled_at=scheduled_at,
        send_limit=send_limit,
        status=CampaignStatus.SCHEDULED if scheduled_at else CampaignStatus.DRAFT,
        created_by_user_id=actor_user_id,
    )
    session.add(campaign)
    await session.flush()
    await record_audit(
        session,
        action="campaigns.created",
        organization_id=org_id,
        actor_user_id=actor_user_id,
        entity_type="campaign",
        entity_id=campaign.id,
        metadata={"channel": channel.value, "status_set": campaign.member_status},
    )
    return campaign


async def preview(session: AsyncSession, *, org_id: str, campaign_id: str, limit: int = 20) -> dict:
    """How many members match, and a sample of who they are."""

    campaign = await _get_campaign(session, org_id, campaign_id)
    members = await _resolve_segment(session, org_id, campaign)
    sample: list[dict] = []
    for m in members[: max(1, min(limit, 50))]:
        user = await session.get(User, m.user_id)
        sample.append(
            {
                "member_id": m.id,
                "name": await _name(m, user),
                "email": user.email if user and campaign.channel != CampaignChannel.SMS else None,
                "phone": m.phone if campaign.channel == CampaignChannel.SMS else None,
                "status": m.member_status.value
                if hasattr(m.member_status, "value")
                else str(m.member_status),
            }
        )
    return {"count": len(members), "sample": sample}


async def schedule(
    session: AsyncSession,
    *,
    org_id: str,
    campaign_id: str,
    scheduled_at: datetime,
    actor_user_id: str | None = None,
) -> Campaign:
    campaign = await _get_campaign(session, org_id, campaign_id)
    if campaign.status not in {CampaignStatus.DRAFT, CampaignStatus.SCHEDULED}:
        raise HTTPException(
            status_code=409, detail=f"Cannot schedule a '{campaign.status.value}' campaign."
        )
    campaign.scheduled_at = scheduled_at
    campaign.status = CampaignStatus.SCHEDULED
    session.add(campaign)
    await record_audit(
        session,
        action="campaigns.scheduled",
        organization_id=org_id,
        actor_user_id=actor_user_id,
        entity_type="campaign",
        entity_id=campaign.id,
        metadata={"scheduled_at": scheduled_at.isoformat()},
    )
    return campaign


async def cancel(
    session: AsyncSession, *, org_id: str, campaign_id: str, actor_user_id: str | None = None
) -> Campaign:
    campaign = await _get_campaign(session, org_id, campaign_id)
    if campaign.status not in {CampaignStatus.DRAFT, CampaignStatus.SCHEDULED}:
        raise HTTPException(
            status_code=409, detail=f"Cannot cancel a '{campaign.status.value}' campaign."
        )
    campaign.status = CampaignStatus.CANCELLED
    session.add(campaign)
    await record_audit(
        session,
        action="campaigns.cancelled",
        organization_id=org_id,
        actor_user_id=actor_user_id,
        entity_type="campaign",
        entity_id=campaign.id,
    )
    return campaign


# ------------------------------------------------------------------- sending
async def _deliver_member(
    session: AsyncSession,
    *,
    org_id: str,
    campaign: Campaign,
    member: OrganizationMember,
    delivery: CampaignDelivery,
) -> CampaignDelivery:
    """Deliver one campaign to one member; sets the row's terminal status."""

    from app.services.notifications_service import create_notification

    wants_email = campaign.channel in {CampaignChannel.EMAIL, CampaignChannel.BOTH} and member.marketing_email_consent
    wants_in_app = campaign.channel in {CampaignChannel.IN_APP, CampaignChannel.BOTH} and member.marketing_in_app_consent
    wants_sms = campaign.channel == CampaignChannel.SMS and member.marketing_sms_consent and bool(member.phone and member.phone.strip())

    user = await session.get(User, member.user_id)

    in_app_sent = False
    email_sent = False
    sms_sent = False
    if wants_in_app:
        await create_notification(
            session,
            org_id=org_id,
            recipient_user_id=member.user_id,
            category=NotificationKind.CAMPAIGN,
            title=campaign.subject,
            body=campaign.body,
            data={"campaign_id": campaign.id},
        )
        in_app_sent = True

    if wants_email and user is not None and user.email_verified:
        await send_email(user.email, campaign.subject, campaign.body)
        email_sent = True

    if wants_sms:
        from app.services.inbox_channels_service import get_credentials

        credentials = await get_credentials(session, org_id, "sms")
        receipt = await deliver_inbox_message(Channel.SMS, member.phone.strip(), campaign.body, credentials)
        sms_sent = bool(receipt.provider_message_id)

    if in_app_sent or email_sent or sms_sent:
        delivery.status = CampaignDeliveryStatus.SENT
        if sms_sent:
            delivery.channel = CampaignChannel.SMS
        elif in_app_sent and email_sent:
            delivery.channel = CampaignChannel.BOTH
        else:
            delivery.channel = CampaignChannel.IN_APP if in_app_sent else CampaignChannel.EMAIL
        delivery.delivered_at = now_utc()
    else:
        delivery.status = CampaignDeliveryStatus.SUPPRESSED
        delivery.channel = campaign.channel

    return delivery


async def run_campaign(
    session: AsyncSession, *, org_id: str, campaign_id: str, actor_user_id: str | None = None
) -> dict:
    """Send a campaign to its resolved segment. Resumable and idempotent."""

    campaign = await _get_campaign(session, org_id, campaign_id)
    if campaign.status not in {
        CampaignStatus.DRAFT,
        CampaignStatus.SCHEDULED,
        CampaignStatus.SENDING,
    }:
        raise HTTPException(
            status_code=409, detail=f"Cannot send a '{campaign.status.value}' campaign."
        )

    members = await _resolve_segment(session, org_id, campaign)
    members = members[: campaign.send_limit]

    existing = {
        d.member_id: d
        for d in (
            await session.execute(
                select(CampaignDelivery).where(
                    CampaignDelivery.organization_id == org_id,
                    CampaignDelivery.campaign_id == campaign.id,
                )
            )
        )
        .scalars()
        .all()
    }

    campaign.status = CampaignStatus.SENDING
    sent = suppressed = failed = 0
    for member in members:
        delivery = existing.get(member.id)
        if delivery is not None and delivery.status == CampaignDeliveryStatus.SENT:
            continue
        if delivery is None:
            delivery = CampaignDelivery(
                organization_id=org_id,
                campaign_id=campaign.id,
                member_id=member.id,
                status=CampaignDeliveryStatus.PENDING,
                channel=campaign.channel,
            )
            session.add(delivery)
        try:
            await _deliver_member(
                session, org_id=org_id, campaign=campaign, member=member, delivery=delivery
            )
        except Exception as exc:  # noqa: BLE001 - one bad recipient must not block the run
            delivery.status = CampaignDeliveryStatus.FAILED
            delivery.error = str(exc)[:300]
        if delivery.status == CampaignDeliveryStatus.SENT:
            sent += 1
        elif delivery.status == CampaignDeliveryStatus.SUPPRESSED:
            suppressed += 1
        elif delivery.status == CampaignDeliveryStatus.FAILED:
            failed += 1

    campaign.status = CampaignStatus.SENT
    campaign.sent_at = now_utc()
    campaign.sent_count = sent
    session.add(campaign)
    await session.flush()
    await record_audit(
        session,
        action="campaigns.sent",
        organization_id=org_id,
        actor_user_id=actor_user_id,
        entity_type="campaign",
        entity_id=campaign.id,
        metadata={
            "targeted": len(members),
            "sent": sent,
            "suppressed": suppressed,
            "failed": failed,
        },
    )
    return {"targeted": len(members), "sent": sent, "suppressed": suppressed, "failed": failed}


# -------------------------------------------------------------------- queries
async def list_campaigns(session: AsyncSession, *, org_id: str, limit: int = 200) -> list[dict]:
    campaigns = (
        (
            await session.execute(
                select(Campaign)
                .where(Campaign.organization_id == org_id)
                .order_by(sa.cast(Campaign.created_at, sa.DateTime).desc())
                .limit(max(1, min(limit, 500)))
            )
        )
        .scalars()
        .all()
    )
    counts: dict[str, int] = {}
    if campaigns:
        rows = (
            await session.execute(
                select(CampaignDelivery.campaign_id, func.count())
                .select_from(CampaignDelivery)
                .where(CampaignDelivery.organization_id == org_id)
                .group_by(CampaignDelivery.campaign_id)
            )
        ).all()
        counts = {cid: int(n) for cid, n in rows}
    return [{"campaign": c, "deliveries": counts.get(c.id, 0)} for c in campaigns]


async def campaign_detail(
    session: AsyncSession, *, org_id: str, campaign_id: str, limit: int = 200
) -> dict:
    campaign = await _get_campaign(session, org_id, campaign_id)
    deliveries = (
        (
            await session.execute(
                select(CampaignDelivery)
                .where(
                    CampaignDelivery.organization_id == org_id,
                    CampaignDelivery.campaign_id == campaign_id,
                )
                .order_by(sa.cast(CampaignDelivery.created_at, sa.DateTime).desc())
                .limit(max(1, min(limit, 500)))
            )
        )
        .scalars()
        .all()
    )
    rows: list[dict] = []
    for d in deliveries:
        member = await session.get(OrganizationMember, d.member_id)
        if member is None:
            continue
        user = await session.get(User, member.user_id)
        rows.append(
            {
                "member_id": d.member_id,
                "member_name": await _name(member, user),
                "status": d.status.value if hasattr(d.status, "value") else str(d.status),
                "channel": d.channel.value if hasattr(d.channel, "value") else str(d.channel),
                "delivered_at": d.delivered_at,
                "error": d.error,
            }
        )
    return {"campaign": campaign, "deliveries": rows}


# -------------------------------------------------------------------- worker
async def run_due_campaigns(session: AsyncSession, *, org_id: str) -> dict:
    """Fire every scheduled campaign whose time has come. Resume-safe."""

    now = now_utc()
    due = (
        (
            await session.execute(
                select(Campaign).where(
                    Campaign.organization_id == org_id,
                    Campaign.status == CampaignStatus.SCHEDULED,
                    Campaign.scheduled_at <= now,  # type: ignore[operator]
                )
            )
        )
        .scalars()
        .all()
    )
    total_sent = 0
    for campaign in due:
        out = await run_campaign(session, org_id=org_id, campaign_id=campaign.id)
        total_sent += out["sent"]
    return {"fired": len(due), "sent": total_sent}
