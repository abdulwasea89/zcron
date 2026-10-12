"""Membership plan API routes (Section 6). Web-only management (Section 16)."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_org, get_session, require_capability, require_writable_org
from app.core.constants import PlanStatus
from app.core.industry import OfferKind
from app.core.permissions import Capability
from app.core.tenancy import TenantContext
from app.models.organization import Organization
from app.models.plan import MembershipPlan
from app.schemas.plans import ArchiveRequest, PlanCreate, PlanOut, PlanUpdate
from app.services import plan_summaries
from app.services import plans_service as plans

router = APIRouter()


def _to_out(p: MembershipPlan) -> PlanOut:
    spec = None
    if p.spec_json:
        try:
            spec = json.loads(p.spec_json)
        except ValueError:
            spec = None
    return PlanOut(
        id=p.id, name=p.name, public_description=p.public_description, price=p.price,
        joining_fee=p.joining_fee,
        currency=p.currency, tax_mode=p.tax_mode.value, tax_rate=p.tax_rate,
        billing_type=p.billing_type.value, visibility=p.visibility.value,
        status=p.status.value, featured=p.featured,
        cycle_length=p.cycle_length, cycle_unit=p.cycle_unit,
        pack_size=p.pack_size, validity_days=p.validity_days,
        audience=p.audience, family_capacity=p.family_capacity,
        off_peak_start=p.off_peak_start, off_peak_end=p.off_peak_end,
        included_credits=p.included_credits,
        offer_kind=p.offer_kind or "membership", spec=spec,
        summary=p.summary,
    )


@router.get("", response_model=list[PlanOut])
async def list_plans(
    offer_kind: OfferKind | None = None,
    ctx: TenantContext = Depends(require_capability(Capability.VIEW_PLANS)),
    session: AsyncSession = Depends(get_session),
):
    return [_to_out(p) for p in await plans.list_plans(session, org_id=ctx.org_id, offer_kind=offer_kind)]


@router.post("", response_model=PlanOut, status_code=201, dependencies=[Depends(require_writable_org)])
async def create_plan(
    data: PlanCreate,
    ctx: TenantContext = Depends(require_capability(Capability.CREATE_EDIT_PLANS)),
    org: Organization = Depends(get_org),
    session: AsyncSession = Depends(get_session),
):
    plan = await plans.create_plan(session, org=org, data=data, actor_id=ctx.user_id)
    return _to_out(plan)


@router.patch("/{plan_id}", response_model=PlanOut, dependencies=[Depends(require_writable_org)])
async def update_plan(
    plan_id: str,
    data: PlanUpdate,
    ctx: TenantContext = Depends(require_capability(Capability.CREATE_EDIT_PLANS)),
    session: AsyncSession = Depends(get_session),
):
    plan = await plans.update_plan(session, org_id=ctx.org_id, plan_id=plan_id, data=data, actor_id=ctx.user_id)
    return _to_out(plan)


@router.post("/{plan_id}/summary", response_model=PlanOut)
async def plan_summary(
    plan_id: str,
    refresh: bool = False,
    ctx: TenantContext = Depends(require_capability(Capability.VIEW_PLANS)),
    session: AsyncSession = Depends(get_session),
):
    """Return the plan with its AI-written summary, generating it once if absent.

    Recording is the point: the first viewer pays for the model call, everyone
    after reads the stored text. ``?refresh=true`` forces a regeneration.
    """

    plan = await plan_summaries.ensure_plan_summary(
        session, org_id=ctx.org_id, plan_id=plan_id, refresh=refresh
    )
    return _to_out(plan)


@router.post("/{plan_id}/publish", response_model=PlanOut, dependencies=[Depends(require_writable_org)])
async def publish_plan(
    plan_id: str,
    ctx: TenantContext = Depends(require_capability(Capability.CREATE_EDIT_PLANS)),
    org: Organization = Depends(get_org),
    session: AsyncSession = Depends(get_session),
):
    plan = await plans.publish_plan(session, org=org, plan_id=plan_id, actor_id=ctx.user_id)
    return _to_out(plan)


@router.post("/{plan_id}/pause", response_model=PlanOut, dependencies=[Depends(require_writable_org)])
async def pause_plan(
    plan_id: str,
    ctx: TenantContext = Depends(require_capability(Capability.CREATE_EDIT_PLANS)),
    session: AsyncSession = Depends(get_session),
):
    plan = await plans.set_status(session, org_id=ctx.org_id, plan_id=plan_id, status=PlanStatus.PAUSED, actor_id=ctx.user_id)
    return _to_out(plan)


@router.post("/{plan_id}/resume", response_model=PlanOut, dependencies=[Depends(require_writable_org)])
async def resume_plan(
    plan_id: str,
    ctx: TenantContext = Depends(require_capability(Capability.CREATE_EDIT_PLANS)),
    session: AsyncSession = Depends(get_session),
):
    plan = await plans.set_status(session, org_id=ctx.org_id, plan_id=plan_id, status=PlanStatus.PUBLISHED, actor_id=ctx.user_id)
    return _to_out(plan)


@router.post("/{plan_id}/duplicate", response_model=PlanOut, status_code=201, dependencies=[Depends(require_writable_org)])
async def duplicate_plan(
    plan_id: str,
    ctx: TenantContext = Depends(require_capability(Capability.CREATE_EDIT_PLANS)),
    session: AsyncSession = Depends(get_session),
):
    plan = await plans.duplicate_plan(session, org_id=ctx.org_id, plan_id=plan_id, actor_id=ctx.user_id)
    return _to_out(plan)


@router.post("/{plan_id}/archive", response_model=PlanOut, dependencies=[Depends(require_writable_org)])
async def archive_plan(
    plan_id: str,
    data: ArchiveRequest | None = None,
    ctx: TenantContext = Depends(require_capability(Capability.ARCHIVE_PLANS)),
    session: AsyncSession = Depends(get_session),
):
    plan = await plans.archive_plan(
        session, org_id=ctx.org_id, plan_id=plan_id,
        replacement_plan_id=data.replacement_plan_id if data else None,
        actor_id=ctx.user_id,
    )
    return _to_out(plan)


@router.post("/{plan_id}/unarchive", response_model=PlanOut, dependencies=[Depends(require_writable_org)])
async def unarchive_plan(
    plan_id: str,
    ctx: TenantContext = Depends(require_capability(Capability.ARCHIVE_PLANS)),
    session: AsyncSession = Depends(get_session),
):
    plan = await plans.unarchive_plan(session, org_id=ctx.org_id, plan_id=plan_id, actor_id=ctx.user_id)
    return _to_out(plan)


@router.delete("/{plan_id}", status_code=204, dependencies=[Depends(require_writable_org)])
async def delete_plan(
    plan_id: str,
    ctx: TenantContext = Depends(require_capability(Capability.ARCHIVE_PLANS)),
    session: AsyncSession = Depends(get_session),
):
    await plans.delete_plan(session, org_id=ctx.org_id, plan_id=plan_id, actor_id=ctx.user_id)
