"""Admin referral program and member referral-code endpoints."""

from __future__ import annotations

import json
from decimal import Decimal

from fastapi import APIRouter, Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session, require_capability, require_role, require_writable_org
from app.core.constants import Role
from app.core.permissions import Capability
from app.core.tenancy import TenantContext
from app.models.organization import Organization
from app.models.referral import ReferralReward
from app.schemas.referrals import (
    MemberReferralOverview,
    ReferralAdminOverview,
    ReferralProgramOut,
    ReferralProgramUpdate,
    ReferralRewardOut,
)
from app.services import idempotency_service, referrals_service

router = APIRouter()


@router.get("/program", response_model=ReferralProgramOut)
async def get_program(
    ctx: TenantContext = Depends(require_capability(Capability.MANAGE_MEMBERS)),
    session: AsyncSession = Depends(get_session),
):
    program = await referrals_service.program_for_org(session, org_id=ctx.org_id)
    return ReferralProgramOut(
        enabled=bool(program and program.enabled),
        reward_description=program.reward_description if program else "A referral reward",
        reward_amount=Decimal(program.reward_amount_minor if program else 0) / 100,
        reward_currency=program.reward_currency if program else "USD",
    )


@router.put("/program", response_model=ReferralProgramOut)
async def update_program(
    data: ReferralProgramUpdate,
    ctx: TenantContext = Depends(require_capability(Capability.MANAGE_MEMBERS)),
    org: Organization = Depends(require_writable_org),
    session: AsyncSession = Depends(get_session),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    claim = await idempotency_service.claim(
        session, key=idempotency_key or "", endpoint="referrals.program.update",
        body=data.model_dump(), organization_id=ctx.org_id, user_id=ctx.user_id,
    )
    if not claim.claimed:
        return ReferralProgramOut.model_validate(json.loads(claim.cached_response or "{}"))
    program = await referrals_service.set_program(
        session, org_id=ctx.org_id, actor_id=ctx.user_id, data=data,
    )
    result = ReferralProgramOut(
        enabled=program.enabled, reward_description=program.reward_description,
        reward_amount=Decimal(program.reward_amount_minor) / 100,
        reward_currency=program.reward_currency,
    )
    await idempotency_service.complete(session, claim.record, code=200, body=result.model_dump_json())
    return result


@router.get("", response_model=ReferralAdminOverview)
async def admin_overview(
    ctx: TenantContext = Depends(require_capability(Capability.MANAGE_MEMBERS)),
    session: AsyncSession = Depends(get_session),
):
    program = await referrals_service.program_for_org(session, org_id=ctx.org_id)
    return await referrals_service.admin_overview(session, org_id=ctx.org_id, program=program)


@router.get("/me", response_model=MemberReferralOverview)
async def member_overview(
    ctx: TenantContext = Depends(require_role(Role.MEMBER)),
    session: AsyncSession = Depends(get_session),
):
    return await referrals_service.member_overview(session, org_id=ctx.org_id, user_id=ctx.user_id)


@router.post("/rewards/{reward_id}/fulfill", response_model=ReferralRewardOut)
async def fulfill_reward(
    reward_id: str,
    ctx: TenantContext = Depends(require_capability(Capability.MANAGE_MEMBERS)),
    org: Organization = Depends(require_writable_org),
    session: AsyncSession = Depends(get_session),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    claim = await idempotency_service.claim(
        session, key=idempotency_key or "", endpoint=f"referrals.reward.fulfill:{reward_id}",
        body={}, organization_id=ctx.org_id, user_id=ctx.user_id,
    )
    if not claim.claimed:
        return ReferralRewardOut.model_validate(json.loads(claim.cached_response or "{}"))
    reward: ReferralReward = await referrals_service.fulfill_reward(
        session, org_id=ctx.org_id, reward_id=reward_id, actor_id=ctx.user_id,
    )
    result = ReferralRewardOut(
        id=reward.id, description=reward.description, status=reward.status,
        earned_at=reward.earned_at, fulfilled_at=reward.fulfilled_at,
        amount_minor=reward.amount_minor, currency=reward.currency,
    )
    await idempotency_service.complete(session, claim.record, code=200, body=result.model_dump_json())
    return result
