"""Analytics API routes (Section 16).

Headline metrics are available to any staff member (mobile dashboard); full
revenue analytics require the view_revenue_analytics capability (owner/manager).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field
from sqlmodel import select

from app.api.deps import get_session, get_tenant, require_capability
from app.core.permissions import Capability
from app.core.tenancy import TenantContext
from app.schemas.analytics import HeadlineMetrics, RevenueAnalytics
from app.services import analytics_service as analytics
from app.models.membership import OrganizationMember

router = APIRouter()


class DashboardHideIn(BaseModel):
    key: str = Field(min_length=1, max_length=300, pattern=r"^\S.*$")


async def _dashboard_member(session: AsyncSession, ctx: TenantContext) -> OrganizationMember:
    if not ctx.is_staff:
        raise HTTPException(status_code=403, detail="Staff only.")
    member = (await session.execute(select(OrganizationMember).where(
        OrganizationMember.organization_id == ctx.org_id,
        OrganizationMember.user_id == ctx.user_id,
    ).with_for_update())).scalar_one_or_none()
    if member is None:
        raise HTTPException(status_code=404, detail="Staff membership not found.")
    return member


@router.get("/dashboard/hidden-attention")
async def hidden_attention(ctx: TenantContext = Depends(get_tenant), session: AsyncSession = Depends(get_session)):
    member = await _dashboard_member(session, ctx)
    return {"keys": member.dashboard_hidden_attention}


@router.post("/dashboard/hidden-attention")
async def hide_attention(data: DashboardHideIn, ctx: TenantContext = Depends(get_tenant), session: AsyncSession = Depends(get_session)):
    member = await _dashboard_member(session, ctx)
    member.dashboard_hidden_attention = list(dict.fromkeys([*member.dashboard_hidden_attention, data.key]))[-200:]
    session.add(member)
    return {"keys": member.dashboard_hidden_attention}


@router.delete("/dashboard/hidden-attention")
async def restore_attention(ctx: TenantContext = Depends(get_tenant), session: AsyncSession = Depends(get_session)):
    member = await _dashboard_member(session, ctx)
    member.dashboard_hidden_attention = []
    session.add(member)
    return {"keys": []}


@router.get("/headline", response_model=HeadlineMetrics, response_model_exclude_none=True)
async def headline(
    ctx: TenantContext = Depends(get_tenant),
    session: AsyncSession = Depends(get_session),
):
    if not ctx.is_staff:
        raise HTTPException(status_code=403, detail="Staff only.")
    data = await analytics.headline_metrics(session, org_id=ctx.org_id)
    return HeadlineMetrics(**data)


@router.get("/revenue", response_model=RevenueAnalytics)
async def revenue(
    ctx: TenantContext = Depends(require_capability(Capability.VIEW_REVENUE_ANALYTICS)),
    session: AsyncSession = Depends(get_session),
):
    data = await analytics.revenue_analytics(session, org_id=ctx.org_id)
    return RevenueAnalytics(**data)
