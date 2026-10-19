"""Inactivity-ladder API routes (#35).

Read the ladder + a member's firing history with ``VIEW_RETENTION`` (owner/
manager). Editing rungs needs ``MANAGE_SETTINGS`` (owner).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session, require_capability
from app.core.permissions import Capability
from app.core.tenancy import TenantContext
from app.schemas.ladder import (
    LadderRungOut,
    LadderRungUpdateIn,
    MemberLadderOut,
)
from app.services import inactivity_ladder_service as ladder

router = APIRouter()


def _rung_out(r) -> LadderRungOut:
    return LadderRungOut(
        day=r.day,
        code=r.code,
        name=r.name,
        member_action=r.member_action,
        staff_action=r.staff_action,
        email_subject=r.email_subject,
        email_body=r.email_body,
        is_active=r.is_active,
    )


@router.get("/config", response_model=list[LadderRungOut])
async def get_config(
    ctx: TenantContext = Depends(require_capability(Capability.VIEW_RETENTION)),
    session: AsyncSession = Depends(get_session),
):
    return [_rung_out(r) for r in await ladder.get_config(session, org_id=ctx.org_id)]


@router.get("/roster", response_model=list[MemberLadderOut])
async def roster(
    ctx: TenantContext = Depends(require_capability(Capability.VIEW_RETENTION)),
    session: AsyncSession = Depends(get_session),
):
    """Current inactivity episodes for active members, with their rung state."""
    return [MemberLadderOut(**row) for row in await ladder.ladder_roster(session, org_id=ctx.org_id)]


@router.patch("/config/{day}", response_model=LadderRungOut)
async def update_rung(
    day: int,
    data: LadderRungUpdateIn,
    ctx: TenantContext = Depends(require_capability(Capability.MANAGE_SETTINGS)),
    session: AsyncSession = Depends(get_session),
):
    rung = await ladder.update_rung(
        session,
        org_id=ctx.org_id,
        day=day,
        member_action=data.member_action,
        staff_action=data.staff_action,
        email_subject=data.email_subject,
        email_body=data.email_body,
        is_active=data.is_active,
        actor_user_id=ctx.user_id,
    )
    return _rung_out(rung)


@router.get("/members/{member_id}", response_model=MemberLadderOut)
async def member_ladder(
    member_id: str,
    ctx: TenantContext = Depends(require_capability(Capability.VIEW_RETENTION)),
    session: AsyncSession = Depends(get_session),
):
    return MemberLadderOut(**await ladder.member_ladder(session, org_id=ctx.org_id, member_id=member_id))


@router.post("/members/{member_id}/rungs/{day}/complete", response_model=MemberLadderOut)
async def complete_rung(
    member_id: str,
    day: int,
    skip: bool = Query(default=False),
    ctx: TenantContext = Depends(require_capability(Capability.VIEW_RETENTION)),
    session: AsyncSession = Depends(get_session),
):
    await ladder.complete_rung(
        session,
        org_id=ctx.org_id,
        member_id=member_id,
        day=day,
        actor_user_id=ctx.user_id,
        skip=skip,
    )
    return MemberLadderOut(**await ladder.member_ladder(session, org_id=ctx.org_id, member_id=member_id))
