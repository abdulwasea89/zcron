"""Segmented campaign API routes (#39).

Owners/managers (``RUN_CAMPAIGNS``) compose campaigns, preview how many members
a segment resolves to, schedule or send them, and read delivery outcomes.
Members are recipients only — deliveries surface in their notification feed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session, require_capability
from app.core.permissions import Capability
from app.core.tenancy import TenantContext
from app.schemas.campaign import (
    CampaignCreateIn,
    CampaignDeliveryOut,
    CampaignDetailOut,
    CampaignListOut,
    CampaignOut,
    CampaignPreviewMember,
    CampaignPreviewOut,
    CampaignRunOut,
    CampaignScheduleIn,
)
from app.services import campaign_service as campaigns

router = APIRouter()


@router.post("", response_model=CampaignOut, status_code=201)
async def create_campaign(
    data: CampaignCreateIn,
    ctx: TenantContext = Depends(require_capability(Capability.RUN_CAMPAIGNS)),
    session: AsyncSession = Depends(get_session),
):
    campaign = await campaigns.create_campaign(
        session,
        org_id=ctx.org_id,
        actor_user_id=ctx.user_id,
        title=data.title,
        subject=data.subject,
        body=data.body,
        channel=data.channel,
        member_status=data.member_status,
        plan_id=data.plan_id,
        min_days_since_last_visit=data.min_days_since_last_visit,
        scheduled_at=data.scheduled_at,
        send_limit=data.send_limit,
        whatsapp_template_sid=data.whatsapp_template_sid,
        whatsapp_variables=data.whatsapp_variables,
        member_tag=data.member_tag,
    )
    return CampaignOut.model_validate(campaign)


@router.get("/preview/{campaign_id}", response_model=CampaignPreviewOut)
async def preview_campaign(
    campaign_id: str,
    limit: int = Query(default=20, ge=1, le=50),
    ctx: TenantContext = Depends(require_capability(Capability.RUN_CAMPAIGNS)),
    session: AsyncSession = Depends(get_session),
):
    data = await campaigns.preview(session, org_id=ctx.org_id, campaign_id=campaign_id, limit=limit)
    return CampaignPreviewOut(
        count=data["count"],
        sample=[CampaignPreviewMember(**m) for m in data["sample"]],
    )


@router.post("/{campaign_id}/schedule", response_model=CampaignOut)
async def schedule_campaign(
    campaign_id: str,
    data: CampaignScheduleIn,
    ctx: TenantContext = Depends(require_capability(Capability.RUN_CAMPAIGNS)),
    session: AsyncSession = Depends(get_session),
):
    campaign = await campaigns.schedule(
        session,
        org_id=ctx.org_id,
        campaign_id=campaign_id,
        scheduled_at=data.scheduled_at,
        actor_user_id=ctx.user_id,
    )
    return CampaignOut.model_validate(campaign)


@router.post("/{campaign_id}/send", response_model=CampaignRunOut)
async def send_campaign(
    campaign_id: str,
    ctx: TenantContext = Depends(require_capability(Capability.RUN_CAMPAIGNS)),
    session: AsyncSession = Depends(get_session),
):
    return CampaignRunOut(
        **await campaigns.run_campaign(
            session, org_id=ctx.org_id, campaign_id=campaign_id, actor_user_id=ctx.user_id
        )
    )


@router.post("/{campaign_id}/cancel", response_model=CampaignOut)
async def cancel_campaign(
    campaign_id: str,
    ctx: TenantContext = Depends(require_capability(Capability.RUN_CAMPAIGNS)),
    session: AsyncSession = Depends(get_session),
):
    campaign = await campaigns.cancel(
        session, org_id=ctx.org_id, campaign_id=campaign_id, actor_user_id=ctx.user_id
    )
    return CampaignOut.model_validate(campaign)


@router.get("", response_model=list[CampaignListOut])
async def list_campaigns(
    limit: int = Query(default=200, ge=1, le=500),
    ctx: TenantContext = Depends(require_capability(Capability.RUN_CAMPAIGNS)),
    session: AsyncSession = Depends(get_session),
):
    rows = await campaigns.list_campaigns(session, org_id=ctx.org_id, limit=limit)
    out: list[CampaignListOut] = []
    for row in rows:
        item = CampaignOut.model_validate(row["campaign"]).model_dump()
        item["deliveries"] = row["deliveries"]
        out.append(CampaignListOut(**item))
    return out


@router.get("/{campaign_id}", response_model=CampaignDetailOut)
async def campaign_detail(
    campaign_id: str,
    limit: int = Query(default=200, ge=1, le=500),
    ctx: TenantContext = Depends(require_capability(Capability.RUN_CAMPAIGNS)),
    session: AsyncSession = Depends(get_session),
):
    data = await campaigns.campaign_detail(
        session, org_id=ctx.org_id, campaign_id=campaign_id, limit=limit
    )
    item = CampaignOut.model_validate(data["campaign"]).model_dump()
    return CampaignDetailOut(
        **item,
        deliveries=[CampaignDeliveryOut(**d) for d in data["deliveries"]],
    )
