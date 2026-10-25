"""Public website inquiry intake stays tenant-scoped and consent-safe."""

import pytest
from sqlalchemy import select

from app.core.rate_limit import rate_limiter
from app.models.lead import Lead
from app.models.organization import Organization


@pytest.fixture(autouse=True)
def local_rate_limiter(monkeypatch):
    async def hit(key, limit, window_seconds):
        return rate_limiter._memory.hit(key, limit, window_seconds)

    monkeypatch.setattr(rate_limiter, "hit", hit)


@pytest.mark.asyncio
async def test_public_inquiry_creates_unconsented_web_form_lead(client, db):
    org = Organization(name="Form Gym", org_code="FORM-GYM", industry="gym")
    db.add(org)
    await db.commit()

    info = await client.get("/api/v1/leads/public/FORM-GYM")
    assert info.status_code == 200
    assert info.json() == {"organization_name": "Form Gym"}

    response = await client.post(
        "/api/v1/leads/public/FORM-GYM",
        json={"name": "  Alex Rivera ", "email": " ALEX@example.com ", "goal": "Build strength"},
    )
    assert response.status_code == 201, response.text
    assert set(response.json()) == {"message"}

    lead = (await db.execute(select(Lead).where(Lead.organization_id == org.id))).scalar_one()
    assert (lead.name, lead.email, lead.goal, lead.source) == (
        "Alex Rivera", "alex@example.com", "Build strength", "web_form",
    )
    assert lead.email_followup_consent is False
    assert lead.sms_followup_consent is False


@pytest.mark.asyncio
async def test_public_inquiry_duplicate_and_honeypot_do_not_expose_or_create_leads(client, db):
    org = Organization(name="Form Gym", org_code="FORM-GYM-2", industry="gym")
    db.add(org)
    await db.commit()
    path = "/api/v1/leads/public/FORM-GYM-2"
    payload = {"name": "Alex", "phone": "+15551234567"}

    first = await client.post(path, json=payload)
    duplicate = await client.post(path, json=payload)
    spam = await client.post(path, json={**payload, "email": "bot@example.com", "website": "spam"})
    assert first.status_code == duplicate.status_code == spam.status_code == 201
    assert first.json() == duplicate.json() == spam.json()
    leads = (await db.execute(select(Lead).where(Lead.organization_id == org.id))).scalars().all()
    assert len(leads) == 1


@pytest.mark.asyncio
async def test_public_inquiry_requires_contact_and_rate_limits(client, db, monkeypatch):
    org = Organization(name="Form Gym", org_code="FORM-GYM-3", industry="gym")
    db.add(org)
    await db.commit()

    invalid = await client.post("/api/v1/leads/public/FORM-GYM-3", json={"name": "Alex"})
    assert invalid.status_code == 422

    from app.api.v1.routes import leads as leads_route

    async def limited(*args, **kwargs):
        return False, 0

    monkeypatch.setattr(leads_route.rate_limiter, "hit", limited)
    limited_response = await client.post(
        "/api/v1/leads/public/FORM-GYM-3", json={"name": "Alex", "email": "alex@example.com"},
    )
    assert limited_response.status_code == 429
    assert not (await db.execute(select(Lead).where(Lead.organization_id == org.id))).scalars().all()
