"""Facebook Lead Ads intake through the saved Page connection."""

import hashlib
import hmac
import json
import re

import httpx
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.constants import LeadSource
from app.core.security import now_utc
from app.models.organization import Organization
from app.models.staff import Task
from app.realtime import events
from app.schemas.leads import LeadCreate
from app.services import idempotency_service, leads_service
from app.services.audit_service import record_audit


def meta_lead_fields(payload: dict) -> LeadCreate:
    if not isinstance(payload.get("field_data"), list):
        raise HTTPException(status_code=502, detail="Meta returned invalid lead fields.")
    fields = {}
    for field in payload.get("field_data", []):
        if not isinstance(field, dict):
            continue
        values = field.get("values")
        if isinstance(values, list) and values and isinstance(values[0], str):
            fields[str(field.get("name", "")).lower()] = values[0].strip()
    name = fields.get("full_name") or " ".join(filter(None, [fields.get("first_name"), fields.get("last_name")]))
    try:
        data = LeadCreate(name=name or "Facebook prospect", email=fields.get("email") or None,
                          phone=fields.get("phone_number") or None,
                          goal=fields.get("fitness_goal") or fields.get("goal") or None,
                          source=LeadSource.FACEBOOK)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail="Meta lead fields are invalid. Check the configured form.") from exc
    if not (data.email or data.phone):
        raise HTTPException(status_code=422, detail="The configured lead form must supply an email address or phone number.")
    if data.email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", data.email):
        raise HTTPException(status_code=422, detail="The configured lead form supplied an invalid email address.")
    return data


async def capture_meta_lead(session: AsyncSession, *, org_id: str, credentials: dict, value: dict) -> str | None:
    forms = set(str(credentials.get("lead_form_ids", "")).split(",")) - {""}
    page_id = str(value.get("page_id", ""))
    form_id = str(value.get("form_id", ""))
    lead_id = str(value.get("leadgen_id", ""))
    if not forms or page_id != credentials.get("sender_id") or form_id not in forms:
        return None
    if not re.fullmatch(r"\d{1,32}", lead_id):
        raise HTTPException(status_code=400, detail="Invalid Meta lead identifier.")
    claim = await idempotency_service.claim(
        session, key=f"meta-lead:{page_id}:{lead_id}", endpoint=f"leads.meta:{org_id}",
        body={"lead_id": lead_id, "form_id": form_id}, organization_id=org_id,
    )
    if not claim.claimed:
        return json.loads(claim.cached_response or "{}").get("lead_id")
    token = credentials.get("page_access_token", "")
    proof = hmac.new(credentials.get("app_secret", "").encode(), token.encode(), hashlib.sha256).hexdigest()
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                f"https://graph.facebook.com/{settings.inbox_meta_graph_version}/{lead_id}",
                params={"fields": "id,form_id,field_data", "appsecret_proof": proof},
                headers={"Authorization": f"Bearer {token}"},
            )
        response.raise_for_status()
        payload = response.json()
        if (not isinstance(payload, dict) or str(payload.get("id")) != lead_id
                or str(payload.get("form_id")) != form_id or not isinstance(payload.get("field_data"), list)):
            raise ValueError("Unexpected lead response")
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="Meta could not supply this lead. Check the Page token and lead-retrieval access.") from exc
    data = meta_lead_fields(payload)
    org = await session.get(Organization, org_id, with_for_update=True, populate_existing=True)
    if org is None:
        raise HTTPException(status_code=404, detail="Workspace not found.")
    lead = await leads_service.find_matching_lead(session, org_id=org_id, email=data.email, phone=data.phone)
    matched = lead is not None
    if lead is None:
        lead = await leads_service.create_lead(session, org_id=org_id, actor_id=None, data=data)
        lead.profile_sources = {field: "meta_lead_ads" for field in lead.profile_sources}
        session.add(lead)
    else:
        # Resubmissions need staff attention without replacing existing profiles, stages, or consent.
        task = Task(organization_id=org_id, category="lead_capture", deadline=now_utc(),
                    title=f"New Facebook inquiry: {data.name}"[:120],
                    description=f"An existing lead submitted Facebook form {form_id}. Review {lead.name} in Leads. Incoming contact: {data.email or ''} {data.phone or ''}.")
        session.add(task)
        await session.flush()
        await events.task_changed(org_id, task_id=task.id, action="created")
    await record_audit(session, action="lead.ad_inquiry_received", organization_id=org_id,
                       entity_type="lead", entity_id=lead.id,
                       metadata={"provider": "meta", "form_id": form_id, "provider_lead_id": lead_id,
                                 "matched_existing": matched})
    await idempotency_service.complete(session, claim.record, code=200, body=json.dumps({"lead_id": lead.id}))
    return lead.id
