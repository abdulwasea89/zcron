"""Retention API routes (#33, #34).

Attendance-drop detection and the churn-risk roster. Owner/manager only
(``VIEW_RETENTION``): these are intervention lists, not member-facing data.
"""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session, require_capability, require_writable_org
from app.core.permissions import Capability
from app.core.tenancy import TenantContext
from app.schemas.retention import MemberRiskOut, RetentionSummaryOut, RetentionWinOut, RetentionCaseUpdate
from app.services import retention_service as retention
from app.services import retention_cases_service as cases

router = APIRouter()


@router.get("/cases")
async def retention_cases(
    include_closed: bool = False,
    ctx: TenantContext = Depends(require_capability(Capability.VIEW_RETENTION)),
    session: AsyncSession = Depends(get_session),
):
    return await cases.list_cases(session, org_id=ctx.org_id, include_closed=include_closed)


@router.put("/cases/{member_id}", dependencies=[Depends(require_writable_org)])
async def save_retention_case(
    member_id: str, data: RetentionCaseUpdate,
    ctx: TenantContext = Depends(require_capability(Capability.VIEW_RETENTION)),
    session: AsyncSession = Depends(get_session),
):
    task = await cases.save_case(session, org_id=ctx.org_id, member_id=member_id, data=data, actor_id=ctx.user_id)
    return {"id": task.id, "done": task.done, "outcome": task.case_outcome}


@router.get("/summary", response_model=RetentionSummaryOut)
async def summary(
    ctx: TenantContext = Depends(require_capability(Capability.VIEW_RETENTION)),
    session: AsyncSession = Depends(get_session),
):
    return RetentionSummaryOut(**await retention.retention_summary(session, org_id=ctx.org_id))


@router.get("/wins", response_model=list[RetentionWinOut])
async def wins(
    limit: int = Query(default=10, ge=1, le=100),
    ctx: TenantContext = Depends(require_capability(Capability.VIEW_RETENTION)),
    session: AsyncSession = Depends(get_session),
):
    return await retention.retention_wins(session, org_id=ctx.org_id, limit=limit)


@router.get("/at-risk", response_model=list[MemberRiskOut])
async def at_risk(
    min_score: int = Query(default=1, ge=0, le=100),
    limit: int = Query(default=100, ge=1, le=500),
    ctx: TenantContext = Depends(require_capability(Capability.VIEW_RETENTION)),
    session: AsyncSession = Depends(get_session),
):
    rows = await retention.risk_roster(
        session, org_id=ctx.org_id, min_score=min_score, limit=limit
    )
    return [MemberRiskOut(**asdict(r)) for r in rows]


@router.get("/drops", response_model=list[MemberRiskOut])
async def drops(
    limit: int = Query(default=100, ge=1, le=500),
    ctx: TenantContext = Depends(require_capability(Capability.VIEW_RETENTION)),
    session: AsyncSession = Depends(get_session),
):
    """Members trending below their own attendance baseline (#33)."""

    rows = await retention.attendance_drops(session, org_id=ctx.org_id, limit=limit)
    return [MemberRiskOut(**asdict(r)) for r in rows]


@router.get("/members/{member_id}", response_model=MemberRiskOut)
async def member_risk(
    member_id: str,
    ctx: TenantContext = Depends(require_capability(Capability.VIEW_RETENTION)),
    session: AsyncSession = Depends(get_session),
):
    risk = await retention.member_risk(session, org_id=ctx.org_id, member_id=member_id)
    return MemberRiskOut(**asdict(risk))
