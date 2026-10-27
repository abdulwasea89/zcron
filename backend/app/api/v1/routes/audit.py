"""Audit log viewer routes (Section 16.1)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session, require_capability
from app.core.permissions import Capability, role_has
from app.core.tenancy import TenantContext
from app.models.audit_log import AuditLog
from app.models.organization import Organization
from app.schemas.audit import AuditActionGroup, AuditLogOut, AuditLogPage
from app.services import audit_service as audit

router = APIRouter()


@router.get("/integrity")
async def audit_integrity(
    ctx: TenantContext = Depends(require_capability(Capability.VIEW_AUDIT_LOG)),
    session: AsyncSession = Depends(get_session),
):
    org = await session.get(Organization, ctx.org_id)
    entries = (await session.execute(
        select(AuditLog).where(AuditLog.organization_id == ctx.org_id)
    )).scalars().all()
    return audit.verify_audit_chain(entries, org.audit_chain_head if org else None)


@router.get("", response_model=AuditLogPage)
async def list_audit_logs(
    action: str | None = Query(default=None),
    entity_type: str | None = Query(default=None),
    entity_id: str | None = Query(default=None),
    actor_user_id: str | None = Query(default=None),
    search: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    ctx: TenantContext = Depends(require_capability(Capability.VIEW_AUDIT_LOG)),
    session: AsyncSession = Depends(get_session),
):
    items, total = await audit.list_audit_logs(
        session,
        organization_id=ctx.org_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        actor_user_id=actor_user_id,
        search=search,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
    )
    if not role_has(ctx.role, Capability.VIEW_STAFF_COMPENSATION):
        for item in items:
            if item["action"].startswith(("payroll.", "staff.compensation_")):
                item.update(old_values=None, new_values=None, metadata={"redacted": True})
    return AuditLogPage(
        items=[AuditLogOut(**i) for i in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=max(1, (total + page_size - 1) // page_size),
    )


@router.get("/actions", response_model=list[AuditActionGroup])
async def list_actions(
    ctx: TenantContext = Depends(require_capability(Capability.VIEW_AUDIT_LOG)),
    session: AsyncSession = Depends(get_session),
):
    return await audit.distinct_actions(session, organization_id=ctx.org_id)
