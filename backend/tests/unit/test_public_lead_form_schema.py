import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from starlette.requests import Request

from app.api.v1.routes import leads as leads_route
from app.api.v1.routes.leads import PublicLeadInquiry
from app.core.constants import LeadSource
from app.models.organization import Organization


def test_public_inquiry_requires_contact_and_normalizes_email_and_phone():
    inquiry = PublicLeadInquiry(
        name=" Alex Rivera ", email=" ALEX@example.com ", phone=" +1 (555) 123-4567 ",
    )
    assert inquiry.name == "Alex Rivera"
    assert inquiry.email == "alex@example.com"
    assert inquiry.phone == "+1 (555) 123-4567"
    assert "email_followup_consent" not in inquiry.model_dump()

    with pytest.raises(ValidationError):
        PublicLeadInquiry(name="Alex")
    with pytest.raises(ValidationError):
        PublicLeadInquiry(name="Alex", email="invalid")
    with pytest.raises(ValidationError):
        PublicLeadInquiry(name="Alex", phone="123")


@pytest.mark.asyncio
async def test_public_route_passes_only_unconsented_gym_leads(monkeypatch):
    org = Organization(name="Test Gym", org_code="TEST-GYM", industry="gym")
    captured = []

    class Result:
        def scalar_one_or_none(self):
            return org

    class Session:
        async def execute(self, _query):
            return Result()

    async def allowed(*_args, **_kwargs):
        return True, 4

    async def capture(_session, **kwargs):
        captured.append(kwargs)

    monkeypatch.setattr(leads_route.rate_limiter, "hit", allowed)
    monkeypatch.setattr(leads_route.leads_service, "create_lead", capture)
    request = Request({
        "type": "http", "method": "POST", "path": "/api/v1/leads/public/TEST-GYM",
        "headers": [], "client": ("127.0.0.1", 1000), "server": ("test", 80),
        "scheme": "http", "query_string": b"",
    })
    result = await leads_route.submit_public_inquiry(
        "TEST-GYM", PublicLeadInquiry(name="Alex", email="alex@example.com"), request, Session(),
    )
    assert result == {"message": "Thanks. Your inquiry has been received."}
    lead_data = captured[0]["data"]
    assert captured[0]["org_id"] == org.id
    assert captured[0]["actor_id"] is None
    assert lead_data.source == LeadSource.WEB_FORM
    assert not lead_data.email_followup_consent and not lead_data.sms_followup_consent


@pytest.mark.asyncio
async def test_public_route_honeypot_and_rate_limit_do_not_create_leads(monkeypatch):
    org = Organization(name="Test Gym", org_code="TEST-GYM", industry="gym")
    captures = []

    class Result:
        def scalar_one_or_none(self):
            return org

    class Session:
        async def execute(self, _query):
            return Result()

    async def allowed(*_args, **_kwargs):
        return True, 4

    async def create(_session, **kwargs):
        captures.append(kwargs)

    monkeypatch.setattr(leads_route.rate_limiter, "hit", allowed)
    monkeypatch.setattr(leads_route.leads_service, "create_lead", create)
    request = Request({"type": "http", "method": "POST", "path": "/", "headers": [], "client": ("127.0.0.1", 1000), "server": ("test", 80), "scheme": "http", "query_string": b""})
    result = await leads_route.submit_public_inquiry(
        "TEST-GYM", PublicLeadInquiry(name="Bot", email="bot@example.com", website="filled"), request, Session(),
    )
    assert result == {"message": "Thanks. Your inquiry has been received."}
    assert captures == []

    async def denied(*_args, **_kwargs):
        return False, 0

    monkeypatch.setattr(leads_route.rate_limiter, "hit", denied)
    with pytest.raises(HTTPException) as exc:
        await leads_route.submit_public_inquiry(
            "TEST-GYM", PublicLeadInquiry(name="Alex", email="alex@example.com"), request, Session(),
        )
    assert exc.value.status_code == 429
    assert captures == []
