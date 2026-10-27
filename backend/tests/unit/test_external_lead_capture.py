import asyncio
import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlmodel import Session, SQLModel, select
from starlette.requests import Request

from app.api.v1.routes import leads as leads_route
from app.models.lead import Lead, LeadFollowUp
from app.models.organization import Organization
from app.services import lead_capture_service as capture


def test_google_ads_payload_maps_contact_fields():
    lead = capture.google_lead_fields({"user_column_data": [
        {"column_id": "FIRST_NAME", "string_value": "Amina"},
        {"column_id": "LAST_NAME", "string_value": "Khan"},
        {"column_id": "EMAIL", "string_value": "AMINA@example.com"},
        {"column_id": "PHONE_NUMBER", "string_value": "+1 555 010 2030"},
        {"column_id": "UNRECOGNIZED", "string_value": "ignored"},
    ]})
    assert lead.name == "Amina Khan"
    assert lead.email == "amina@example.com"
    assert lead.phone == "+15550102030"
    assert lead.source == "google"
    assert not lead.email_followup_consent and not lead.sms_followup_consent


def test_tiktok_relay_requires_contact_and_maps_source():
    lead = capture.tiktok_lead_fields({"data": {
        "id": "tiktok-1", "full_name": "Sam Rivera", "email": "sam@example.com", "goal": "Strength",
    }})
    assert lead.name == "Sam Rivera" and lead.email == "sam@example.com"
    assert lead.goal == "Strength" and lead.source == "tiktok"
    assert capture.tiktok_lead_fields({"name": "Form lead", "email": "f@example.com", "source": "web_form"}).source == "web_form"
    with pytest.raises(HTTPException, match="must provide"):
        capture.tiktok_lead_fields({"name": "No contact"})


@pytest.mark.asyncio
async def test_google_webhook_rejects_wrong_key_and_accepts_provider_test(monkeypatch):
    async def connection(*_args):
        return SimpleNamespace(webhook_token="secret")

    monkeypatch.setattr(leads_route, "_ad_connection", connection)

    def make_request(payload):
        body = json.dumps(payload).encode()
        async def receive(): return {"type": "http.request", "body": body, "more_body": False}
        return Request({"type": "http", "method": "POST", "headers": []}, receive)

    with pytest.raises(HTTPException) as exc:
        await leads_route.google_ads_lead_webhook("gym", make_request({"google_key": "wrong"}), None)
    assert exc.value.status_code == 403
    assert await leads_route.google_ads_lead_webhook(
        "gym", make_request({"google_key": "secret", "is_test": True}), None,
    ) == {"ok": True, "test": True}


def test_external_lead_capture_is_idempotent_and_tenant_scoped():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            class AsyncSessionFacade:
                def get_bind(self): return db.get_bind()
                async def get(self, *args, **kwargs): return db.get(*args, **kwargs)
                async def execute(self, statement): return db.execute(statement)
                async def flush(self): db.flush()
                def add(self, row): db.add(row)

            session = AsyncSessionFacade()
            org = Organization(name="External Leads", org_code="EXTERNAL-LEADS")
            db.add(org)
            db.commit()
            data = capture.google_lead_fields({"user_column_data": [
                {"column_id": "FULL_NAME", "string_value": "Amina Khan"},
                {"column_id": "EMAIL", "string_value": "amina@example.com"},
            ]})
            first = asyncio.run(capture.capture_provider_lead(
                session, org_id=org.id, provider="google_ads", lead_id="lead-001", data=data,
            ))
            db.commit()
            replay = asyncio.run(capture.capture_provider_lead(
                session, org_id=org.id, provider="google_ads", lead_id="lead-001", data=data,
            ))
            db.commit()
            leads = db.exec(select(Lead).where(Lead.organization_id == org.id)).all()
            followups = db.exec(select(LeadFollowUp).where(LeadFollowUp.organization_id == org.id)).all()
            assert first == replay == leads[0].id
            assert len(leads) == 1 and len(followups) == 4
            assert leads[0].source == "google" and leads[0].email_followup_consent is False
    finally:
        engine.dispose()
