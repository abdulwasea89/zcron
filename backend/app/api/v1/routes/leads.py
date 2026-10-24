"""Sales lead directory and qualification profiles."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session, require_capability, require_writable_org
from app.core.permissions import Capability
from app.core.tenancy import TenantContext
from app.models.organization import Organization
from app.schemas.leads import (
    LeadBookingCreate,
    LeadBookingOut,
    LeadBookingStatusUpdate,
    LeadCreate,
    LeadFollowUpOut,
    LeadFollowUpUpdate,
    LeadHistoryOut,
    LeadMissedCallOut,
    LeadOut,
    LeadUpdate,
    TrialSlotOut,
)
from app.services import idempotency_service, leads_service

router = APIRouter()


@router.post("/{lead_id}/missed-call", response_model=LeadMissedCallOut)
async def log_missed_call(
    lead_id: str,
    ctx: TenantContext = Depends(require_capability(Capability.MANAGE_MEMBERS)),
    org: Organization = Depends(require_writable_org),
    session: AsyncSession = Depends(get_session),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    claim = await idempotency_service.claim(
        session, key=idempotency_key or "", endpoint=f"leads.missed_call:{lead_id}",
        body={"lead_id": lead_id}, organization_id=ctx.org_id, user_id=ctx.user_id,
    )
    if not claim.claimed:
        return LeadMissedCallOut.model_validate_json(claim.cached_response or "{}")
    result = await leads_service.log_missed_call(
        session, org_id=ctx.org_id, lead_id=lead_id, actor_id=ctx.user_id,
        idempotency_key=idempotency_key or "",
    )
    output = LeadMissedCallOut(**result)
    await idempotency_service.complete(session, claim.record, code=200, body=output.model_dump_json())
    return output


@router.get("/trial-slots", response_model=list[TrialSlotOut])
async def trial_slots(
    ctx: TenantContext = Depends(require_capability(Capability.MANAGE_MEMBERS)),
    session: AsyncSession = Depends(get_session),
):
    return await leads_service.list_trial_slots(session, org_id=ctx.org_id)


@router.get("/{lead_id}/history", response_model=LeadHistoryOut)
async def lead_history(
    lead_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    ctx: TenantContext = Depends(require_capability(Capability.MANAGE_MEMBERS)),
    session: AsyncSession = Depends(get_session),
):
    return await leads_service.stage_history(
        session, org_id=ctx.org_id, lead_id=lead_id, page=page, page_size=page_size,
    )


@router.get("/{lead_id}/followups", response_model=list[LeadFollowUpOut])
async def list_lead_followups(
    lead_id: str,
    ctx: TenantContext = Depends(require_capability(Capability.MANAGE_MEMBERS)),
    session: AsyncSession = Depends(get_session),
):
    return await leads_service.list_lead_followups(session, org_id=ctx.org_id, lead_id=lead_id)


@router.patch(
    "/{lead_id}/followups/{followup_id}", response_model=LeadFollowUpOut,
)
async def update_lead_followup(
    lead_id: str,
    followup_id: str,
    data: LeadFollowUpUpdate,
    ctx: TenantContext = Depends(require_capability(Capability.MANAGE_MEMBERS)),
    org: Organization = Depends(require_writable_org),
    session: AsyncSession = Depends(get_session),
):
    return await leads_service.update_lead_followup(
        session, org_id=ctx.org_id, lead_id=lead_id, followup_id=followup_id,
        actor_id=ctx.user_id, status=data.status, note=data.note,
    )


@router.get("", response_model=list[LeadOut])
async def list_leads(ctx: TenantContext = Depends(require_capability(Capability.MANAGE_MEMBERS)),
                     session: AsyncSession = Depends(get_session)):
    return await leads_service.list_leads(session, org_id=ctx.org_id)


@router.post("", response_model=LeadOut, status_code=201)
async def create_lead(data: LeadCreate, ctx: TenantContext = Depends(require_capability(Capability.MANAGE_MEMBERS)),
                      org: Organization = Depends(require_writable_org),
                      session: AsyncSession = Depends(get_session),
                      idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    claim = await idempotency_service.claim(session, key=idempotency_key or "", endpoint="leads.create",
                                            body=data.model_dump(mode="json"), organization_id=ctx.org_id, user_id=ctx.user_id)
    if not claim.claimed:
        return LeadOut.model_validate(json.loads(claim.cached_response or "{}"))
    lead = await leads_service.create_lead(session, org_id=ctx.org_id, actor_id=ctx.user_id, data=data)
    output = LeadOut.model_validate(lead)
    await idempotency_service.complete(session, claim.record, code=201, body=output.model_dump_json())
    return output


@router.get("/{lead_id}", response_model=LeadOut)
async def get_lead(lead_id: str, ctx: TenantContext = Depends(require_capability(Capability.MANAGE_MEMBERS)),
                   session: AsyncSession = Depends(get_session)):
    return await leads_service.get_lead(session, org_id=ctx.org_id, lead_id=lead_id)


@router.get("/{lead_id}/bookings", response_model=list[LeadBookingOut])
async def list_lead_bookings(
    lead_id: str,
    ctx: TenantContext = Depends(require_capability(Capability.MANAGE_MEMBERS)),
    session: AsyncSession = Depends(get_session),
):
    return await leads_service.list_lead_bookings(session, org_id=ctx.org_id, lead_id=lead_id)


@router.post("/{lead_id}/bookings", response_model=LeadBookingOut, status_code=201)
async def create_lead_booking(
    lead_id: str,
    data: LeadBookingCreate,
    ctx: TenantContext = Depends(require_capability(Capability.MANAGE_MEMBERS)),
    org: Organization = Depends(require_writable_org),
    session: AsyncSession = Depends(get_session),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    body = data.model_dump(mode="json")
    claim = await idempotency_service.claim(
        session,
        key=idempotency_key or "",
        endpoint=f"leads.booking.create:{lead_id}",
        body=body,
        organization_id=ctx.org_id,
        user_id=ctx.user_id,
    )
    if not claim.claimed:
        return LeadBookingOut.model_validate(json.loads(claim.cached_response or "{}"))
    booking = await leads_service.create_lead_booking(
        session,
        org_id=ctx.org_id,
        actor_id=ctx.user_id,
        lead_id=lead_id,
        booking_type=data.booking_type,
        class_session_id=data.class_session_id,
        trainer_member_id=data.trainer_member_id,
        starts_at=data.starts_at,
        ends_at=data.ends_at,
        notes=data.notes,
    )
    output = LeadBookingOut.model_validate(booking)
    await idempotency_service.complete(session, claim.record, code=201, body=output.model_dump_json())
    return output


@router.patch("/{lead_id}/bookings/{booking_id}", response_model=LeadBookingOut)
async def update_lead_booking(
    lead_id: str,
    booking_id: str,
    data: LeadBookingStatusUpdate,
    ctx: TenantContext = Depends(require_capability(Capability.MANAGE_MEMBERS)),
    org: Organization = Depends(require_writable_org),
    session: AsyncSession = Depends(get_session),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    body = data.model_dump(mode="json")
    claim = await idempotency_service.claim(
        session,
        key=idempotency_key or "",
        endpoint=f"leads.booking.update:{booking_id}",
        body=body,
        organization_id=ctx.org_id,
        user_id=ctx.user_id,
    )
    if not claim.claimed:
        return LeadBookingOut.model_validate(json.loads(claim.cached_response or "{}"))
    booking = await leads_service.update_lead_booking_status(
        session,
        org_id=ctx.org_id,
        actor_id=ctx.user_id,
        lead_id=lead_id,
        booking_id=booking_id,
        status=data.status,
    )
    output = LeadBookingOut.model_validate(booking)
    await idempotency_service.complete(session, claim.record, code=200, body=output.model_dump_json())
    return output


@router.patch("/{lead_id}", response_model=LeadOut)
async def update_lead(lead_id: str, data: LeadUpdate,
                      ctx: TenantContext = Depends(require_capability(Capability.MANAGE_MEMBERS)),
                      org: Organization = Depends(require_writable_org),
                      session: AsyncSession = Depends(get_session),
                      idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    claim = await idempotency_service.claim(session, key=idempotency_key or "", endpoint=f"leads.update:{lead_id}",
                                            body=data.model_dump(exclude_unset=True, mode="json"),
                                            organization_id=ctx.org_id, user_id=ctx.user_id)
    if not claim.claimed:
        return LeadOut.model_validate(json.loads(claim.cached_response or "{}"))
    lead = await leads_service.update_lead(session, org_id=ctx.org_id, actor_id=ctx.user_id,
                                           lead_id=lead_id, data=data)
    output = LeadOut.model_validate(lead)
    await idempotency_service.complete(session, claim.record, code=200, body=output.model_dump_json())
    return output
