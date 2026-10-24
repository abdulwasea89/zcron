"""Integration tests for front-desk visitors & lockers (#22).

Covers day-pass logging (with a payment), guest log listing, check-out,
idempotency, lockers (create/assign/release/dup), summary, tenant isolation and
capability enforcement.
"""

from __future__ import annotations

import uuid

import pytest
from sqlmodel import select

from app.core.constants import PaymentKind
from app.models.payment import Payment
from tests.helpers import OWNER_PROFILE, latest_code_for

PASSWORD = "Sup3rStr0ng!Pass"
MEMBER_PWD = "M3mberStr0ng!Pwd"


async def _provision_gym(client, *, owner_email="owner@fd.com"):
    await client.post("/api/v1/auth/register", json={
        "full_name": "Alex", "email": owner_email,
        "password": PASSWORD, "confirm_password": PASSWORD, **OWNER_PROFILE})
    code = latest_code_for(owner_email)
    await client.post("/api/v1/auth/verify-email", json={"email": owner_email, "code": code})
    r = await client.post("/api/v1/organizations/register", json={
        "owner_email": owner_email,
        "details": {"name": "Iron Pulse Boxing", "default_currency": "USD"},
        "tier": "pro"})
    body = r.json()
    org_id = body["organization"]["id"]
    headers = {"Authorization": f"Bearer {body['access_token']}", "X-Organization-Id": org_id}
    return headers, org_id, body["organization"]["org_code"]


async def _signup_member(client, org_code, email):
    await client.post("/api/v1/memberships/signup/request-email",
                      json={"org_code": org_code, "email": email})
    code = latest_code_for(email)
    await client.post("/api/v1/memberships/signup/verify-email",
                      json={"org_code": org_code, "email": email, "code": code})
    r = await client.post("/api/v1/memberships/signup/set-password",
                          json={"org_code": org_code, "email": email, "password": MEMBER_PWD})
    return r.json()["member_id"]


async def _member_headers(client, org_code, email):
    r = await client.post("/api/v1/auth/member-login",
                          json={"org_code": org_code, "email": email, "password": MEMBER_PWD})
    body = r.json()
    return {"Authorization": f"Bearer {body['access_token']}",
            "X-Organization-Id": body["organization_id"]}


# ------------------------------------------------------------------- visitors
@pytest.mark.asyncio
async def test_log_day_pass_creates_visitor_and_payment(client, db):
    headers, org_id, _code = await _provision_gym(client)
    r = await client.post("/api/v1/front-desk/visitors", headers=headers, json={
        "name": "Walkin Wanda", "phone": "+92300", "kind": "day_pass",
        "amount": 10.0, "method": "cash"})
    assert r.status_code == 201, r.text
    v = r.json()
    assert v["kind"] == "day_pass"
    assert v["paid"] is True
    assert v["amount"] == 10.0
    assert v["checked_out_at"] is None

    # The day pass is in the payment ledger.
    payments = (
        await db.execute(select(Payment).where(Payment.organization_id == org_id))
    ).scalars().all()
    assert len(payments) == 1
    assert payments[0].kind == PaymentKind.DAY_PASS
    assert payments[0].amount == 10.0
    assert payments[0].member_id is None

    r = await client.get("/api/v1/front-desk/visitors", headers=headers)
    assert [x["name"] for x in r.json()] == ["Walkin Wanda"]


@pytest.mark.asyncio
async def test_walk_in_creates_consent_free_lead_but_known_member_does_not(client):
    headers, _org_id, org_code = await _provision_gym(client)
    r = await client.post("/api/v1/front-desk/visitors", headers=headers, json={
        "name": "Prospect Pat", "email": "pat@walkin.com", "phone": "+923001234567",
        "kind": "walk_in",
    })
    assert r.status_code == 201, r.text
    leads = await client.get("/api/v1/leads", headers=headers)
    assert leads.status_code == 200 and len(leads.json()) == 1
    assert leads.json()[0]["source"] == "walk_in"
    assert leads.json()[0]["email_followup_consent"] is False
    assert leads.json()[0]["sms_followup_consent"] is False

    await _signup_member(client, org_code, "existing@walkin.com")
    r = await client.post("/api/v1/front-desk/visitors", headers=headers, json={
        "name": "Existing Member", "email": "existing@walkin.com", "kind": "walk_in",
    })
    assert r.status_code == 201, r.text
    leads = await client.get("/api/v1/leads", headers=headers)
    assert len(leads.json()) == 1


@pytest.mark.asyncio
async def test_log_visitor_is_idempotent(client):
    headers, _org_id, _code = await _provision_gym(client)
    key = str(uuid.uuid4())
    h = {**headers, "Idempotency-Key": key}
    r1 = await client.post("/api/v1/front-desk/visitors", headers=h, json={"name": "Guest G", "kind": "guest"})
    r2 = await client.post("/api/v1/front-desk/visitors", headers=h, json={"name": "Guest G", "kind": "guest"})
    assert r1.status_code == 201 and r2.status_code == 201, (r1.text, r2.text)
    assert r1.json()["id"] == r2.json()["id"]
    r = await client.get("/api/v1/front-desk/visitors", headers=headers)
    assert len(r.json()) == 1


@pytest.mark.asyncio
async def test_guest_of_member_and_checkout(client):
    headers, _org_id, org_code = await _provision_gym(client)
    member_id = await _signup_member(client, org_code, "host@fd.com")

    r = await client.post("/api/v1/front-desk/visitors", headers=headers, json={
        "name": "Guest", "kind": "guest", "host_member_id": member_id})
    assert r.status_code == 201, r.text
    v = r.json()
    assert v["host_member_id"] == member_id
    assert v["host_name"]

    r = await client.post(f"/api/v1/front-desk/visitors/{v['id']}/check-out", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["checked_out_at"] is not None


@pytest.mark.asyncio
async def test_summary(client):
    headers, _org_id, _code = await _provision_gym(client)
    await client.post("/api/v1/front-desk/visitors", headers=headers,
                      json={"name": "A", "kind": "day_pass", "amount": 12.0, "method": "cash"})
    await client.post("/api/v1/front-desk/visitors", headers=headers, json={"name": "B", "kind": "walk_in"})
    r = await client.get("/api/v1/front-desk/summary", headers=headers)
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["visitors_today"] == 2
    assert s["inside_now"] == 2
    assert s["day_pass_revenue"] == 12.0


# -------------------------------------------------------------------- lockers
@pytest.mark.asyncio
async def test_locker_lifecycle(client):
    headers, _org_id, _code = await _provision_gym(client)
    r = await client.post("/api/v1/front-desk/lockers", headers=headers, json={"number": "12"})
    assert r.status_code == 201, r.text
    locker_id = r.json()["id"]
    assert r.json()["status"] == "free"

    # Duplicate number is rejected.
    r = await client.post("/api/v1/front-desk/lockers", headers=headers, json={"number": "12"})
    assert r.status_code == 409, r.text

    r = await client.post(f"/api/v1/front-desk/lockers/{locker_id}/assign",
                          headers=headers, json={"holder_label": "Wanda"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "occupied"
    assert r.json()["holder_label"] == "Wanda"

    # Assigning an occupied locker conflicts.
    r = await client.post(f"/api/v1/front-desk/lockers/{locker_id}/assign",
                          headers=headers, json={"holder_label": "Someone"})
    assert r.status_code == 409, r.text

    r = await client.post(f"/api/v1/front-desk/lockers/{locker_id}/release", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "free"
    assert r.json()["holder_label"] is None


# --------------------------------------------------------------------- guards
@pytest.mark.asyncio
async def test_tenant_isolation(client):
    headers_a, _org_a, _code_a = await _provision_gym(client, owner_email="a@fd.com")
    r = await client.post("/api/v1/front-desk/visitors", headers=headers_a, json={"name": "A"})
    visitor_id = r.json()["id"]

    headers_b, *_ = await _provision_gym(client, owner_email="b@fd.com")
    r = await client.post(f"/api/v1/front-desk/visitors/{visitor_id}/check-out", headers=headers_b)
    assert r.status_code == 404, r.text


@pytest.mark.asyncio
async def test_member_cannot_use_front_desk(client):
    headers, _org_id, org_code = await _provision_gym(client)
    await _signup_member(client, org_code, "m@fd.com")
    mh = await _member_headers(client, org_code, "m@fd.com")
    r = await client.get("/api/v1/front-desk/visitors", headers=mh)
    assert r.status_code == 403, r.text
