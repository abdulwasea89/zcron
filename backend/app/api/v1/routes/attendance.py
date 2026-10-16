"""Attendance API routes (Section 1.3, #18).

Front-desk check-in, the live "today" feed, per-member visit history and the
console summary. Check-in is idempotent (Security Rule #2): the client sends an
``Idempotency-Key`` and a double-tap replays the first result.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.api.deps import get_org, get_session, get_tenant, require_capability
from app.core.permissions import Capability
from app.core.tenancy import IDEMPOTENCY_HEADER, TenantContext
from app.models.membership import OrganizationMember
from app.models.organization import Organization
from app.schemas.attendance import (
    AttendanceMember,
    AttendanceCardAssign,
    AttendanceCardCheckIn,
    AttendanceOut,
    AttendanceSummary,
    CheckInCreate,
    CheckInOut,
    SyncIn,
    SyncOut,
    SyncResult,
)
from app.services import attendance_service as attendance
from app.services.audit_service import record_audit

router = APIRouter()


def _normalize_card_uid(card_uid: str) -> str:
    # RFID readers commonly emit hexadecimal UIDs with varying case/spaces.
    normalized = "".join(card_uid.split()).upper()
    if len(normalized) < 3 or len(normalized) > 128 or any(ord(c) < 33 for c in normalized):
        raise HTTPException(status_code=422, detail="Enter a valid card identifier.")
    return normalized


@router.post("/card/check-in", response_model=CheckInOut, status_code=201)
async def card_check_in(
    data: AttendanceCardCheckIn,
    idempotency_key: str = Header(default="", alias=IDEMPOTENCY_HEADER),
    ctx: TenantContext = Depends(require_capability(Capability.TAKE_ATTENDANCE)),
    session: AsyncSession = Depends(get_session),
):
    """Resolve an organization-scoped card UID and record a card check-in."""
    card_uid = _normalize_card_uid(data.card_uid)
    member = (
        await session.execute(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == ctx.org_id,
                OrganizationMember.attendance_card_uid == card_uid,
            )
        )
    ).scalar_one_or_none()
    if member is None:
        raise HTTPException(status_code=404, detail="This card is not linked to a member in this workspace.")
    result = await attendance.record_checkin(
        session,
        org_id=ctx.org_id,
        member_id=member.id,
        method="card",
        actor_user_id=ctx.user_id,
        idempotency_key=idempotency_key or None,
    )
    return CheckInOut(**result)


@router.put("/members/{member_id}/card", status_code=204)
async def assign_attendance_card(
    member_id: str,
    data: AttendanceCardAssign,
    ctx: TenantContext = Depends(require_capability(Capability.MANAGE_MEMBERS)),
    session: AsyncSession = Depends(get_session),
):
    """Assign or replace an RFID card for an organization member."""
    member = await session.get(OrganizationMember, member_id)
    if member is None or member.organization_id != ctx.org_id:
        raise HTTPException(status_code=404, detail="Member not found in this organization.")
    card_uid = _normalize_card_uid(data.card_uid)
    existing = (
        await session.execute(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == ctx.org_id,
                OrganizationMember.attendance_card_uid == card_uid,
                OrganizationMember.id != member_id,
            )
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="This card is already linked to another member.")
    had_card = bool(member.attendance_card_uid)
    member.attendance_card_uid = card_uid
    session.add(member)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail="This card is already linked to another member.") from exc
    await record_audit(
        session,
        action="attendance.card.assigned",
        organization_id=ctx.org_id,
        actor_user_id=ctx.user_id,
        entity_type="member",
        entity_id=member.id,
        metadata={"replaced": had_card, "card_uid_last4": card_uid[-4:]},
    )
    return Response(status_code=204)


@router.delete("/members/{member_id}/card", status_code=204)
async def remove_attendance_card(
    member_id: str,
    ctx: TenantContext = Depends(require_capability(Capability.MANAGE_MEMBERS)),
    session: AsyncSession = Depends(get_session),
):
    """Unlink a lost or retired card from a member."""
    member = await session.get(OrganizationMember, member_id)
    if member is None or member.organization_id != ctx.org_id:
        raise HTTPException(status_code=404, detail="Member not found in this organization.")
    had_card = bool(member.attendance_card_uid)
    member.attendance_card_uid = None
    session.add(member)
    if had_card:
        await record_audit(
            session,
            action="attendance.card.removed",
            organization_id=ctx.org_id,
            actor_user_id=ctx.user_id,
            entity_type="member",
            entity_id=member.id,
        )
    return Response(status_code=204)


@router.get("/members", response_model=list[AttendanceMember])
async def search_members(
    q: str = "",
    ctx: TenantContext = Depends(require_capability(Capability.TAKE_ATTENDANCE)),
    org: Organization = Depends(get_org),
    session: AsyncSession = Depends(get_session),
):
    """Search members by name/email/phone for the check-in box.

    Uses ``TAKE_ATTENDANCE`` (front desk included) rather than the admin member
    directory, which front desk cannot read. Each hit carries its status card.
    """

    rows = await attendance.search_members(
        session, org_id=ctx.org_id, q=q, tz_name=org.timezone
    )
    return [AttendanceMember(**r) for r in rows]


@router.get("/roster", response_model=list[AttendanceMember])
async def roster(
    ctx: TenantContext = Depends(require_capability(Capability.TAKE_ATTENDANCE)),
    session: AsyncSession = Depends(get_session),
):
    """Everyone in the org (id/name/email/status) for offline check-in search."""

    rows = await attendance.list_roster(session, org_id=ctx.org_id)
    return [AttendanceMember(**r) for r in rows]


@router.post("/sync", response_model=SyncOut)
async def sync(
    data: SyncIn,
    ctx: TenantContext = Depends(require_capability(Capability.TAKE_ATTENDANCE)),
    session: AsyncSession = Depends(get_session),
):
    """Flush offline-queued check-ins (idempotent per item)."""

    results: list[SyncResult] = []
    for item in data.items:
        try:
            res = await attendance.record_checkin(
                session,
                org_id=ctx.org_id,
                member_id=item.member_id,
                method=item.method,
                actor_user_id=ctx.user_id,
                idempotency_key=item.idempotency_key,
                checked_in_at=item.checked_in_at,
            )
            results.append(SyncResult(id=item.id, status="synced", attendance_id=res["id"]))
        except HTTPException as e:
            results.append(SyncResult(id=item.id, status="error", detail=str(e.detail)))
    return SyncOut(results=results)


@router.post("/check-in", response_model=CheckInOut, status_code=201)
async def check_in(
    data: CheckInCreate,
    idempotency_key: str = Header(default="", alias=IDEMPOTENCY_HEADER),
    ctx: TenantContext = Depends(require_capability(Capability.TAKE_ATTENDANCE)),
    session: AsyncSession = Depends(get_session),
):
    """Log a member visit (manual or QR) and return status-on-check-in."""

    result = await attendance.record_checkin(
        session,
        org_id=ctx.org_id,
        member_id=data.member_id,
        method=data.method,
        actor_user_id=ctx.user_id,
        note=data.note,
        idempotency_key=idempotency_key or None,
    )
    return CheckInOut(**result)


@router.get("/today", response_model=list[AttendanceOut])
async def today(
    ctx: TenantContext = Depends(get_tenant),
    org: Organization = Depends(get_org),
    session: AsyncSession = Depends(get_session),
):
    if not ctx.is_staff:
        raise HTTPException(status_code=403, detail="Staff only.")
    rows = await attendance.list_today(session, org_id=ctx.org_id, tz_name=org.timezone)
    return [AttendanceOut(**r) for r in rows]


@router.get("/members/{member_id}/visits", response_model=list[AttendanceOut])
async def member_visits(
    member_id: str,
    ctx: TenantContext = Depends(get_tenant),
    session: AsyncSession = Depends(get_session),
):
    if not ctx.is_staff:
        raise HTTPException(status_code=403, detail="Staff only.")
    rows = await attendance.list_for_member(session, org_id=ctx.org_id, member_id=member_id)
    return [AttendanceOut(**r) for r in rows]


@router.get("/summary", response_model=AttendanceSummary)
async def summary(
    ctx: TenantContext = Depends(get_tenant),
    org: Organization = Depends(get_org),
    session: AsyncSession = Depends(get_session),
):
    if not ctx.is_staff:
        raise HTTPException(status_code=403, detail="Staff only.")
    data = await attendance.summary(session, org_id=ctx.org_id, tz_name=org.timezone)
    return AttendanceSummary(**data)
