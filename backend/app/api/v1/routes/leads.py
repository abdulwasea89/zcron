"""Sales lead directory and qualification profiles."""

from __future__ import annotations

import json
import re
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, Request
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.api.deps import get_client_ip, get_session, require_capability, require_writable_org
from app.core.constants import LeadSource
from app.core.permissions import Capability
from app.core.rate_limit import rate_limiter
from app.core.tenancy import TenantContext
from app.models.organization import Organization
from app.schemas.leads import (
    LeadBookingCreate,
    LeadBookingOut,
    LeadBookingStatusUpdate,
    LeadCreate,
    LeadFollowUpOut,
    LeadFollowUpUpdate,
    LeadFirstContactIn,
    LeadHistoryOut,
    LeadMissedCallOut,
    LeadOut,
    LeadSpeedReportOut,
    LeadUpdate,
    TrialSlotOut,
)
from app.services import idempotency_service, leads_service

router = APIRouter()


class PublicLeadInquiry(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=40)
    goal: str | None = Field(default=None, max_length=2000)
    website: str = Field(default="", max_length=200)  # honeypot

    @field_validator("name", "goal", "phone")
    @classmethod
    def trim_fields(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str | None) -> str | None:
        if value and len(re.sub(r"\D", "", value)) < 7:
            raise ValueError("Enter a valid phone number.")
        return value

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str | None) -> str | None:
        value = value.strip().lower() if value else None
        if value and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
            raise ValueError("Enter a valid email address.")
        return value

    @model_validator(mode="after")
    def require_contact_method(self):
        if not self.name or not (self.email or self.phone):
            raise ValueError("Enter your name and an email address or phone number.")
        return self


@router.get("/public/{org_code}")
async def public_inquiry_info(
    org_code: Annotated[str, Path(pattern=r"^[A-Za-z0-9-]{1,64}$")],
    session: AsyncSession = Depends(get_session),
):
    org = (await session.execute(select(Organization).where(Organization.org_code == org_code))).scalar_one_or_none()
    if org is None or org.industry not in {"gym", "gym_fitness"}:
        raise HTTPException(status_code=404, detail="This gym’s inquiry form is unavailable.")
    return {"organization_name": org.name}


@router.post("/public/{org_code}", status_code=201)
async def submit_public_inquiry(
    org_code: Annotated[str, Path(pattern=r"^[A-Za-z0-9-]{1,64}$")],
    data: PublicLeadInquiry,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    org = (await session.execute(select(Organization).where(Organization.org_code == org_code))).scalar_one_or_none()
    if org is None or org.industry not in {"gym", "gym_fitness"}:
        raise HTTPException(status_code=404, detail="This gym’s inquiry form is unavailable.")
    allowed, _ = await rate_limiter.hit(
        f"public-lead-form:{org_code}:{get_client_ip(request)}", 5, 60,
    )
    if not allowed:
        raise HTTPException(status_code=429, detail="Please wait a moment before sending another inquiry.")
    if data.website:
        return {"message": "Thanks. Your inquiry has been received."}

    from app.services import leads_service

    try:
        await leads_service.create_lead(
            session, org_id=org.id, actor_id=None,
            data=LeadCreate(
                name=data.name, email=data.email, phone=data.phone,
                goal=data.goal, source=LeadSource.WEB_FORM,
            ),
        )
    except HTTPException as exc:
        # Keep duplicate submissions indistinguishable from successful intake.
        if exc.status_code != 409:
            raise
    return {"message": "Thanks. Your inquiry has been received."}


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


@router.post("/{lead_id}/first-contact", response_model=LeadOut)
async def log_first_contact(
    lead_id: str,
    data: LeadFirstContactIn,
    ctx: TenantContext = Depends(require_capability(Capability.MANAGE_MEMBERS)),
    org: Organization = Depends(require_writable_org),
    session: AsyncSession = Depends(get_session),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    claim = await idempotency_service.claim(
        session, key=idempotency_key or "", endpoint=f"leads.first_contact:{lead_id}",
        body=data.model_dump(mode="json"), organization_id=ctx.org_id, user_id=ctx.user_id,
    )
    if not claim.claimed:
        return LeadOut.model_validate_json(claim.cached_response or "{}")
    lead = await leads_service.log_first_contact(
        session, org_id=ctx.org_id, lead_id=lead_id, actor_id=ctx.user_id, method=data.method,
    )
    output = LeadOut.model_validate(lead)
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


@router.get("/speed-report", response_model=LeadSpeedReportOut)
async def speed_report(
    days: int = Query(default=30, ge=7, le=90),
    ctx: TenantContext = Depends(require_capability(Capability.MANAGE_MEMBERS)),
    session: AsyncSession = Depends(get_session),
):
    return await leads_service.lead_speed_report(session, org_id=ctx.org_id, days=days)


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
