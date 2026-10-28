"""SaaS-tier guardrails: member cap at signup (§3.1) and read-only writes (§3.5).

Both rules protect platform revenue integrity: a gym must not exceed the seats
it pays for, and a delinquent gym drops to read-only (no plan edits, no new
signups, no payroll) until billing is restored.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from sqlmodel import select

from app.core.constants import SaasStatus
from app.models.organization import Organization
from tests.helpers import OWNER_PROFILE, latest_code_for

PASSWORD = "Sup3rStr0ng!Pass"
MEMBER_PWD = "M3mberStr0ng!Pwd"


async def _provision_gym_with_plan(client) -> tuple[str, str, dict]:
    """Owner registers, provisions gym, connects Stripe, publishes a plan."""

    await client.post("/api/v1/auth/register", json={
        "full_name": "Alex", "email": "owner@g.com",
        "password": PASSWORD, "confirm_password": PASSWORD, **OWNER_PROFILE})
    code = latest_code_for("owner@g.com")
    await client.post("/api/v1/auth/verify-email", json={"email": "owner@g.com", "code": code})
    r = await client.post("/api/v1/organizations/register", json={
        "owner_email": "owner@g.com",
        "details": {"name": "Iron Pulse Boxing", "default_currency": "USD"},
        "tier": "pro"})
    body = r.json()
    org_id = body["organization"]["id"]
    org_code = body["organization"]["org_code"]
    access = body["access_token"]
    headers = {"Authorization": f"Bearer {access}", "X-Organization-Id": org_id}

    await client.post("/api/v1/organizations/me/connect", headers=headers)
    await client.post("/api/v1/organizations/me/connect/complete", headers=headers)

    r = await client.post("/api/v1/plans", headers=headers, json={
        "name": "Monthly", "price": 149.0, "billing_type": "recurring",
        "cycle_unit": "month", "cycle_length": 1})
    plan_id = r.json()["id"]
    await client.post(f"/api/v1/plans/{plan_id}/publish", headers=headers)
    return org_id, org_code, plan_id, headers


async def _signup_member_through_payment(client, org_code, plan_id, email) -> int:
    """Run a member through the signup flow up to (and including) payment.

    Returns the HTTP status of the final /pay call so the caller can assert.
    """

    await client.post("/api/v1/memberships/signup/request-email",
                      json={"org_code": org_code, "email": email})
    code = latest_code_for(email)
    await client.post("/api/v1/memberships/signup/verify-email",
                      json={"org_code": org_code, "email": email, "code": code})
    await client.post("/api/v1/memberships/signup/set-password",
                      json={"org_code": org_code, "email": email, "password": MEMBER_PWD})
    r = await client.post("/api/v1/memberships/signup/pay",
                          headers={"Idempotency-Key": str(uuid.uuid4())},
                          json={"org_code": org_code, "email": email, "plan_id": plan_id})
    return r


async def _set_org(db, org_id, **fields):
    org = (await db.execute(select(Organization).where(Organization.id == org_id))).scalar_one()
    for k, v in fields.items():
        setattr(org, k, v)
    db.add(org)
    await db.commit()


@pytest.mark.asyncio
async def test_member_cap_blocks_signup_over_capacity(client, db):
    """With member_cap=1, the first member activates but the second is rejected."""

    org_id, org_code, plan_id, _ = await _provision_gym_with_plan(client)
    await _set_org(db, org_id, member_cap=1)

    r1 = await _signup_member_through_payment(client, org_code, plan_id, "first@member.com")
    assert r1.status_code == 200, r1.text
    assert r1.json()["member_status"] == "active"

    r2 = await _signup_member_through_payment(client, org_code, plan_id, "second@member.com")
    assert r2.status_code == 402, r2.text
    assert "capacity" in r2.json()["detail"].lower()


@pytest.mark.asyncio
async def test_member_cap_allows_up_to_capacity(client, db):
    """A gym at cap=2 admits exactly two members."""

    org_id, org_code, plan_id, _ = await _provision_gym_with_plan(client)
    await _set_org(db, org_id, member_cap=2)

    r1 = await _signup_member_through_payment(client, org_code, plan_id, "a@member.com")
    r2 = await _signup_member_through_payment(client, org_code, plan_id, "b@member.com")
    assert r1.status_code == 200 and r2.status_code == 200, (r1.text, r2.text)


@pytest.mark.asyncio
async def test_read_only_org_blocks_plan_write(client, db):
    """A read-only (past-due grace-ended) org cannot create or edit plans."""

    org_id, org_code, plan_id, headers = await _provision_gym_with_plan(client)
    await _set_org(db, org_id, saas_status=SaasStatus.READ_ONLY)

    r = await client.post("/api/v1/plans", headers=headers, json={
        "name": "New Plan", "price": 99.0, "billing_type": "recurring",
        "cycle_unit": "month", "cycle_length": 1})
    assert r.status_code == 403, r.text
    assert "read-only" in r.json()["detail"].lower()

    # Reads still work.
    r = await client.get("/api/v1/plans", headers=headers)
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_read_only_org_blocks_new_member_signup(client, db):
    """Read-only mode also stops new member signups (§3.5)."""

    org_id, org_code, plan_id, _ = await _provision_gym_with_plan(client)
    await _set_org(db, org_id, saas_status=SaasStatus.READ_ONLY)

    r = await client.post("/api/v1/memberships/signup/start", json={"org_code": org_code})
    assert r.status_code == 403, r.text


@pytest.mark.asyncio
async def test_read_only_org_blocks_cash_logging(client, db):
    """Cash logging is a mutating admin op and must be blocked in read-only."""

    org_id, org_code, plan_id, headers = await _provision_gym_with_plan(client)
    await _set_org(db, org_id, saas_status=SaasStatus.SUSPENDED)

    r = await client.post("/api/v1/cash/log", headers=headers, json={
        "member_id": "some-member-id", "plan_id": plan_id, "amount": 50.0})
    assert r.status_code == 403, r.text


@pytest.mark.asyncio
async def test_active_org_permits_writes(client, db):
    """Sanity: an org in good standing (active) can still create plans."""

    org_id, org_code, plan_id, headers = await _provision_gym_with_plan(client)
    await _set_org(db, org_id, saas_status=SaasStatus.ACTIVE)

    r = await client.post("/api/v1/plans", headers=headers, json={
        "name": "Second Plan", "price": 79.0, "billing_type": "drop_in"})
    assert r.status_code == 201, r.text


@pytest.mark.asyncio
async def test_platform_invoice_failure_is_subscription_scoped_and_event_idempotent(client, db, monkeypatch):
    from app.services import saas_billing_service

    org_id, _org_code, _plan_id, _headers = await _provision_gym_with_plan(client)
    await _set_org(db, org_id, stripe_customer_id="cus_workspace", stripe_subscription_id="sub_workspace",
                   saas_status=SaasStatus.ACTIVE)
    monkeypatch.setattr(saas_billing_service, "_notify_owner", AsyncMock())
    event = {"id": "evt_invoice_failed_once", "type": "invoice.payment_failed",
             "data": {"object": {"customer": "cus_workspace", "subscription": "sub_workspace"}}}

    first = await client.post("/api/v1/webhooks/stripe", json=event)
    replay = await client.post("/api/v1/webhooks/stripe", json=event)
    assert first.status_code == replay.status_code == 200
    org = await db.get(Organization, org_id)
    await db.refresh(org)
    assert org.saas_status == SaasStatus.PAST_DUE
    assert org.saas_retry_count == 0

    wrong_subscription = {"id": "evt_other_subscription", "type": "invoice.payment_failed",
                          "data": {"object": {"customer": "cus_workspace", "subscription": "sub_other"}}}
    response = await client.post("/api/v1/webhooks/stripe", json=wrong_subscription)
    assert response.status_code == 200
    await db.refresh(org)
    assert org.saas_retry_count == 0
