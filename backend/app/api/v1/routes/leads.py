"""Sales lead directory and qualification profiles."""

from __future__ import annotations

import json
import re
import secrets
import hmac
import hashlib
import time
from string import Formatter
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
from app.models.inbox_channel import InboxChannelConnection
from app.core.config import settings
from app.core.security import now_utc
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
from app.services.audit_service import record_audit

router = APIRouter()

_AD_CHANNELS = {"google_ads": "lead_google_ads", "tiktok": "lead_tiktok"}


class TikTokCredentials(BaseModel):
    client_key: str = Field(min_length=1, max_length=200)
    client_secret: str = Field(min_length=1, max_length=500)


class LeadFollowupTemplate(BaseModel):
    subject: str = Field(min_length=1, max_length=120)
    body: str = Field(min_length=1, max_length=2000)
    sms_body: str = Field(min_length=1, max_length=250)

    @field_validator("subject", "body", "sms_body")
    @classmethod
    def trim_template_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Template text cannot be blank.")
        return value

    @model_validator(mode="after")
    def allow_only_name_variable(self):
        try:
            fields = [field for text in (self.subject, self.body, self.sms_body)
                      for _, field, _, _ in Formatter().parse(text) if field]
        except ValueError as exc:
            raise ValueError("Use only the {name} placeholder.") from exc
        if any(field != "name" for field in fields):
            raise ValueError("Use only the {name} placeholder.")
        return self


class LeadFollowupTemplatesIn(BaseModel):
    templates: dict[str, LeadFollowupTemplate]

    @model_validator(mode="after")
    def require_schedule_days(self):
        if set(self.templates) != {"0", "1", "3", "7"}:
            raise ValueError("Provide email templates for days 0, 1, 3, and 7.")
        return self


async def _ad_connection(session: AsyncSession, org_id: str, provider: str):
    channel = _AD_CHANNELS.get(provider)
    if channel is None:
        raise HTTPException(status_code=404, detail="Unsupported lead provider.")
    return (await session.execute(select(InboxChannelConnection).where(
        InboxChannelConnection.organization_id == org_id,
        InboxChannelConnection.channel == channel,
    ))).scalar_one_or_none()


@router.get("/capture-integrations")
async def list_capture_integrations(
    ctx: TenantContext = Depends(require_capability(Capability.MANAGE_SETTINGS)),
    session: AsyncSession = Depends(get_session),
):
    output = {}
    for provider, channel in _AD_CHANNELS.items():
        connection = await _ad_connection(session, ctx.org_id, provider)
        output[provider] = {
            "connected": connection is not None,
            "webhook_url": (
                f"{settings.inbox_public_webhook_base_url.rstrip('/')}/api/v1/leads/webhooks/{provider}/{ctx.org_id}"
                if connection and settings.inbox_public_webhook_base_url else None
            ),
            "secret": connection.webhook_token if connection else None,
            "native_configured": bool(
                provider == "tiktok" and connection and
                _capture_credentials(connection).get("client_key") and
                _capture_credentials(connection).get("client_secret")
            ),
        }
    return output


def _capture_credentials(connection: InboxChannelConnection) -> dict:
    # Older relay connections stored an empty JSON object before credentials were encrypted.
    if connection.credentials_ciphertext == "{}":
        return {}
    from app.services.inbox_channels_service import decrypt_credentials
    return decrypt_credentials(connection)


def _verify_tiktok_signature(raw: bytes, payload: dict, signature: str, credentials: dict) -> bool:
    parts = dict(part.split("=", 1) for part in signature.split(",") if "=" in part)
    timestamp, supplied = parts.get("t", ""), parts.get("s", "")
    if not timestamp.isdigit() or abs(time.time() - int(timestamp)) > 300:
        return False
    expected = hmac.new(credentials["client_secret"].encode(), timestamp.encode() + b"." + raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(supplied, expected) and payload.get("client_key") == credentials.get("client_key")


@router.put("/capture-integrations/tiktok/credentials")
async def configure_tiktok_credentials(
    body: TikTokCredentials,
    ctx: TenantContext = Depends(require_capability(Capability.MANAGE_SETTINGS)),
    session: AsyncSession = Depends(get_session),
):
    connection = await _ad_connection(session, ctx.org_id, "tiktok")
    if connection is None:
        raise HTTPException(status_code=409, detail="Enable TikTok lead capture before configuring its app credentials.")
    from app.services.inbox_channels_service import encrypt_credentials
    credentials = _capture_credentials(connection)
    credentials.update(client_key=body.client_key.strip(), client_secret=body.client_secret.strip())
    connection.credentials_ciphertext = encrypt_credentials(credentials)
    await record_audit(session, action="lead.capture_tiktok_app_configured",
                       organization_id=ctx.org_id, actor_user_id=ctx.user_id,
                       entity_type="lead_capture_integration", entity_id="tiktok")
    return {"native_configured": True}


@router.put("/capture-integrations/{provider}")
async def connect_capture_integration(
    provider: str,
    ctx: TenantContext = Depends(require_capability(Capability.MANAGE_SETTINGS)),
    session: AsyncSession = Depends(get_session),
):
    connection = await _ad_connection(session, ctx.org_id, provider)
    if not settings.inbox_public_webhook_base_url.startswith("https://"):
        raise HTTPException(status_code=422, detail="Configure a public HTTPS API URL before enabling lead webhooks.")
    token = secrets.token_urlsafe(32)
    rotated = connection is not None
    if connection is None:
        connection = InboxChannelConnection(
            organization_id=ctx.org_id, channel=_AD_CHANNELS[provider],
            credentials_ciphertext="{}", webhook_token=token,
        )
    else:
        connection.webhook_token = token
        connection.connected_at = now_utc()
    session.add(connection)
    await session.flush()
    await record_audit(session, action="lead.capture_integration_connected",
                       organization_id=ctx.org_id, actor_user_id=ctx.user_id,
                       entity_type="lead_capture_integration", entity_id=provider,
                       metadata={"provider": provider, "rotated": rotated})
    return {
        "connected": True,
        "webhook_url": f"{settings.inbox_public_webhook_base_url.rstrip('/')}/api/v1/leads/webhooks/{provider}/{ctx.org_id}",
        "secret": token,
    }


@router.delete("/capture-integrations/{provider}", status_code=204)
async def disconnect_capture_integration(
    provider: str,
    ctx: TenantContext = Depends(require_capability(Capability.MANAGE_SETTINGS)),
    session: AsyncSession = Depends(get_session),
):
    connection = await _ad_connection(session, ctx.org_id, provider)
    if connection is not None:
        await session.delete(connection)
        await record_audit(session, action="lead.capture_integration_disconnected",
                           organization_id=ctx.org_id, actor_user_id=ctx.user_id,
                           entity_type="lead_capture_integration", entity_id=provider,
                           metadata={"provider": provider})


async def _provider_body(request: Request) -> tuple[bytes, dict]:
    if int(request.headers.get("content-length", "0") or 0) > 65536:
        raise HTTPException(status_code=413, detail="Lead payload is too large.")
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > 65536:
            raise HTTPException(status_code=413, detail="Lead payload is too large.")
    try:
        body = bytes(raw)
        payload = json.loads(body)
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid lead payload.") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Lead payload must be a JSON object.")
    return body, payload


async def _provider_payload(request: Request) -> dict:
    return (await _provider_body(request))[1]


@router.post("/webhooks/google_ads/{org_id}")
async def google_ads_lead_webhook(org_id: str, request: Request, session: AsyncSession = Depends(get_session)):
    payload = await _provider_payload(request)
    connection = await _ad_connection(session, org_id, "google_ads")
    if not connection or not hmac.compare_digest(str(payload.get("google_key", "")), connection.webhook_token or ""):
        raise HTTPException(status_code=403, detail="Invalid Google Ads lead key.")
    if payload.get("is_test") is True:
        return {"ok": True, "test": True}
    from app.services.lead_capture_service import capture_provider_lead, google_lead_fields
    lead = google_lead_fields(payload)
    lead_id = str(payload.get("lead_id", ""))
    captured_id = await capture_provider_lead(session, org_id=org_id, provider="google_ads", lead_id=lead_id, data=lead)
    await session.commit()
    from app.realtime import events
    await events.publish(org_id, "lead.changed", {"lead_ids": [captured_id]})
    return {"ok": True}


@router.post("/webhooks/tiktok/{org_id}")
async def tiktok_lead_webhook(
    org_id: str, request: Request, session: AsyncSession = Depends(get_session),
):
    raw, payload = await _provider_body(request)
    connection = await _ad_connection(session, org_id, "tiktok")
    if not connection:
        raise HTTPException(status_code=403, detail="TikTok lead capture is not configured.")
    credentials = _capture_credentials(connection)
    signature = request.headers.get("tiktok-signature", "")
    if signature and credentials.get("client_secret"):
        if not _verify_tiktok_signature(raw, payload, signature, credentials):
            raise HTTPException(status_code=403, detail="Invalid TikTok signature.")
        if isinstance(payload.get("content"), str):
            try:
                payload["content"] = json.loads(payload["content"])
            except json.JSONDecodeError as exc:
                raise HTTPException(status_code=400, detail="Invalid TikTok event content.") from exc
    elif not hmac.compare_digest(request.headers.get("x-acron-lead-token", ""), connection.webhook_token or ""):
        raise HTTPException(status_code=403, detail="Invalid lead provider token.")
    from app.services.lead_capture_service import capture_provider_lead, tiktok_lead_fields
    data = tiktok_lead_fields(payload)
    value = payload.get("content") if isinstance(payload.get("content"), dict) else payload
    value = value.get("data") if isinstance(value.get("data"), dict) else value
    lead_id = str(value.get("lead_id") or value.get("id") or payload.get("event_id") or "")
    captured_id = await capture_provider_lead(session, org_id=org_id, provider="tiktok", lead_id=lead_id, data=data)
    await session.commit()
    from app.realtime import events
    await events.publish(org_id, "lead.changed", {"lead_ids": [captured_id]})
    return {"ok": True}


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


@router.get("/followup-templates")
async def get_followup_templates(
    ctx: TenantContext = Depends(require_capability(Capability.MANAGE_SETTINGS)),
    session: AsyncSession = Depends(get_session),
):
    from app.services.lead_followup_delivery import configured_sms_template
    from app.workers.lead_followups import _EMAILS, configured_followup_email

    org = await session.get(Organization, ctx.org_id)
    config = org.lead_followup_templates if org else None
    return {
        str(day): {
            "subject": configured_followup_email(day, config)[0],
            "body": configured_followup_email(day, config)[1],
            "sms_body": configured_sms_template(day, config),
        }
        for day in _EMAILS
    }


@router.put("/followup-templates", dependencies=[Depends(require_writable_org)])
async def update_followup_templates(
    data: LeadFollowupTemplatesIn,
    ctx: TenantContext = Depends(require_capability(Capability.MANAGE_SETTINGS)),
    session: AsyncSession = Depends(get_session),
):
    org = await session.get(Organization, ctx.org_id, with_for_update=True)
    if org is None:
        raise HTTPException(status_code=404, detail="Workspace not found.")
    templates = {day: value.model_dump() for day, value in data.templates.items()}
    if org.lead_followup_templates != templates:
        org.lead_followup_templates = templates
        session.add(org)
        await record_audit(
            session, action="lead.followup_templates_updated", organization_id=ctx.org_id,
            actor_user_id=ctx.user_id, entity_type="organization", entity_id=ctx.org_id,
            metadata={"days": sorted(templates, key=int)},
        )
    return templates


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
