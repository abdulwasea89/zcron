"""Member detail aggregation endpoint (plan + payments + pending payments).

Sections 8, 9.3. The detail page is a web-only admin view gated by
MANAGE_MEMBERS and scoped to the tenant via the JWT org.
"""

from __future__ import annotations

import pytest

from app.models.audit_log import AuditLog
from app.core.constants import PaymentStatus, SubscriptionStatus
from app.models.membership import OrganizationMember
from app.models.payment import Payment
from app.models.subscription import Subscription
from tests.helpers import OWNER_PROFILE, latest_code_for
from sqlmodel import select

PASSWORD = "Sup3rStr0ng!Pass"
MEMBER_PWD = "M3mberStr0ng!Pwd"


async def _provision(client) -> tuple[str, str, dict, str]:
    """Register owner, provision gym, connect Stripe, publish a plan.

    Returns (org_code, plan_id, headers, org_id)."""
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
    org_id, org_code, access = body["organization"]["id"], body["organization"]["org_code"], body["access_token"]
    headers = {"Authorization": f"Bearer {access}", "X-Organization-Id": org_id}

    await client.post("/api/v1/organizations/me/connect", headers=headers)
    await client.post("/api/v1/organizations/me/connect/complete", headers=headers)

    r = await client.post("/api/v1/plans", headers=headers, json={
        "name": "Monthly", "price": 149.0, "billing_type": "recurring",
        "cycle_unit": "month", "cycle_length": 1})
    plan_id = r.json()["id"]
    await client.post(f"/api/v1/plans/{plan_id}/publish", headers=headers)
    return org_code, plan_id, headers, org_id


async def _signup(client, org_code: str, plan_id: str, email: str) -> None:
    await client.post("/api/v1/memberships/signup/request-email",
                      json={"org_code": org_code, "email": email})
    code = latest_code_for(email)
    await client.post("/api/v1/memberships/signup/verify-email",
                      json={"org_code": org_code, "email": email, "code": code})
    await client.post("/api/v1/memberships/signup/set-password",
                      json={"org_code": org_code, "email": email, "password": MEMBER_PWD})


async def _signup_and_pay(client, org_code: str, plan_id: str, email: str) -> dict:
    await _signup(client, org_code, plan_id, email)
    r = await client.post("/api/v1/memberships/signup/pay",
                          headers={"Idempotency-Key": f"idem-{email}"},
                          json={"org_code": org_code, "email": email, "plan_id": plan_id})
    assert r.status_code == 200, r.text
    return r.json()


async def _member_id(client, headers, email: str) -> str:
    r = await client.get("/api/v1/members", headers=headers)
    assert r.status_code == 200, r.text
    for m in r.json():
        if m["email"] == email:
            return m["member_id"]
    raise AssertionError(f"member {email} not in directory")


@pytest.mark.asyncio
async def test_detail_returns_plan_and_payments_and_audits_private_reads(client, db):
    org_code, plan_id, headers, _ = await _provision(client)
    email = "sarah@member.com"
    await _signup_and_pay(client, org_code, plan_id, email)
    member_id = await _member_id(client, headers, email)
    member = await db.get(OrganizationMember, member_id)
    member.health_notes = "Sensitive health note"
    member.id_document_type = "passport"
    member.id_document_last4 = "1234"
    member.emergency_contact = "Emergency contact name · +1 555 0100"
    db.add(member)
    await db.commit()

    r = await client.get(f"/api/v1/members/{member_id}", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["member"]["member_id"] == member_id
    assert body["member"]["email"] == email

    sub = body["subscription"]
    assert sub is not None
    assert sub["plan_name"] == "Monthly"
    assert sub["price_snapshot"] == 149.0
    assert sub["billing_type"] == "recurring"
    assert sub["status"] == "active"
    assert sub["current_period_end"] is not None

    assert len(body["payments"]) == 1
    assert body["payments"][0]["amount"] == 149.0
    assert body["payments"][0]["status"] == "succeeded"

    # Active member with a settled payment has nothing pending.
    assert body["pending_payments"] == []
    assert body["profile"]["health_notes"] == "Sensitive health note"
    audit = (await db.execute(select(AuditLog).where(
        AuditLog.organization_id == member.organization_id,
        AuditLog.action == "member.private_profile_viewed",
        AuditLog.entity_id == member_id,
    ))).scalar_one()
    assert audit.actor_user_id
    assert audit.metadata_json == '{"fields": ["emergency_contact", "health_notes", "id_document"]}'
    assert "Sensitive health note" not in audit.metadata_json


@pytest.mark.asyncio
async def test_cash_payment_appears_in_history(client):
    org_code, plan_id, headers, _ = await _provision(client)
    email = "dan@member.com"
    await _signup_and_pay(client, org_code, plan_id, email)
    member_id = await _member_id(client, headers, email)

    r = await client.post("/api/v1/cash/log", headers={**headers, "Idempotency-Key": "member-detail-cash"}, json={
        "member_id": member_id, "plan_id": plan_id, "amount": 149.0, "method": "cash"})
    assert r.status_code == 201, r.text

    r = await client.get(f"/api/v1/members/{member_id}", headers=headers)
    body = r.json()
    methods = {p["method"] for p in body["payments"]}
    assert methods == {"card", "cash"}
    assert len(body["payments"]) == 2


@pytest.mark.asyncio
async def test_renewal_shown_when_subscription_grace(client, db):
    org_code, plan_id, headers, _ = await _provision(client)
    email = "grace@member.com"
    await _signup_and_pay(client, org_code, plan_id, email)
    member_id = await _member_id(client, headers, email)

    member = await db.get(OrganizationMember, member_id)
    sub = (
        await db.execute(select(Subscription).where(Subscription.member_id == member.id))
    ).scalar_one()
    sub.status = SubscriptionStatus.GRACE
    db.add(sub)
    await db.commit()

    r = await client.get(f"/api/v1/members/{member_id}", headers=headers)
    assert r.status_code == 200, r.text
    pending = r.json()["pending_payments"]
    renewal = [p for p in pending if p["kind"] == "renewal"]
    assert len(renewal) == 1
    assert renewal[0]["amount"] == 149.0
    assert renewal[0]["currency"] == "USD"


@pytest.mark.asyncio
async def test_failed_attempt_shown(client, db):
    org_code, plan_id, headers, org_id = await _provision(client)
    email = "fail@member.com"
    await _signup_and_pay(client, org_code, plan_id, email)
    member_id = await _member_id(client, headers, email)

    member = await db.get(OrganizationMember, member_id)
    db.add(Payment(
        organization_id=org_id, member_id=member.id, plan_id=plan_id,
        kind="member_fee", method="card", status=PaymentStatus.FAILED,
        amount=149.0, currency="USD"))
    await db.commit()

    r = await client.get(f"/api/v1/members/{member_id}", headers=headers)
    pending = r.json()["pending_payments"]
    failed = [p for p in pending if p["kind"] == "failed_attempt"]
    assert len(failed) == 1
    assert failed[0]["amount"] == 149.0


@pytest.mark.asyncio
async def test_pending_payment_member_shows_first_payment(client):
    org_code, plan_id, headers, _ = await _provision(client)
    email = "nopay@member.com"
    await _signup(client, org_code, plan_id, email)  # no pay -> pending_payment
    member_id = await _member_id(client, headers, email)

    r = await client.get(f"/api/v1/members/{member_id}", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["subscription"] is None
    assert body["payments"] == []
    pending = body["pending_payments"]
    first = [p for p in pending if p["kind"] == "first_payment"]
    assert len(first) == 1
    assert first[0]["amount"] is None


@pytest.mark.asyncio
async def test_detail_scoped_to_org(client, db):
    # Second gym owner provisions a different org. Their token must not read
    # another org's member (tenant isolation).
    org_code, plan_id, headers, _ = await _provision(client)
    email = "isola@member.com"
    await _signup_and_pay(client, org_code, plan_id, email)
    member_id = await _member_id(client, headers, email)

    await client.post("/api/v1/auth/register", json={
        "full_name": "Other", "email": "other@g.com",
        "password": PASSWORD, "confirm_password": PASSWORD, **OWNER_PROFILE})
    code = latest_code_for("other@g.com")
    await client.post("/api/v1/auth/verify-email", json={"email": "other@g.com", "code": code})
    r = await client.post("/api/v1/organizations/register", json={
        "owner_email": "other@g.com", "details": {"name": "Other Gym"}, "tier": "starter"})
    other_org_id = r.json()["organization"]["id"]
    other_access = r.json()["access_token"]
    other_headers = {"Authorization": f"Bearer {other_access}", "X-Organization-Id": other_org_id}

    r = await client.get(f"/api/v1/members/{member_id}", headers=other_headers)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_detail_forbidden_for_member_role(client):
    org_code, plan_id, headers, _ = await _provision(client)
    email = "self@member.com"
    login = await _signup_and_pay(client, org_code, plan_id, email)
    member_id = await _member_id(client, headers, email)
    member_org = login["organization_id"]
    member_headers = {"Authorization": f"Bearer {login['access_token']}",
                      "X-Organization-Id": member_org}

    r = await client.get(f"/api/v1/members/{member_id}", headers=member_headers)
    assert r.status_code == 403


async def _provision_trainer(client, headers, email, name="Marcus Trainer") -> str:
    """Invite + redeem a trainer; returns their member_id."""

    r = await client.post("/api/v1/staff/invites", headers=headers,
                          json={"role": "trainer", "email": email})
    invite_code = r.json()["code"]
    await client.post("/api/v1/staff/invites/redeem", json={
        "code": invite_code, "full_name": name, "password": PASSWORD})
    r = await client.get("/api/v1/members", headers=headers, params={"role": "trainer"})
    trainer = [m for m in r.json() if m["email"] == email][0]
    return trainer["member_id"]


@pytest.mark.asyncio
async def test_detail_includes_trainer_assignments(client):
    org_code, plan_id, headers, _ = await _provision(client)
    email = "trained@member.com"
    await _signup_and_pay(client, org_code, plan_id, email)
    member_id = await _member_id(client, headers, email)
    trainer_id = await _provision_trainer(client, headers, "coach@t.com", "Coach First")

    # Before assignment the detail has no trainers.
    r = await client.get(f"/api/v1/members/{member_id}", headers=headers)
    assert r.json()["trainer_assignments"] == []

    # Assign -> appears in detail with id + name.
    r = await client.post(f"/api/v1/members/{member_id}/trainers", headers=headers,
                          json={"trainer_member_id": trainer_id})
    assert r.status_code == 201, r.text
    r = await client.get(f"/api/v1/members/{member_id}", headers=headers)
    assert r.status_code == 200, r.text
    assignments = r.json()["trainer_assignments"]
    assert len(assignments) == 1
    assert assignments[0]["trainer_member_id"] == trainer_id
    assert assignments[0]["trainer_name"] == "Coach First"
    assert assignments[0]["active"] is True

    # Unassign -> gone from detail.
    r = await client.delete(f"/api/v1/members/{member_id}/trainers/{trainer_id}", headers=headers)
    assert r.status_code == 200, r.text
    r = await client.get(f"/api/v1/members/{member_id}", headers=headers)
    assert r.json()["trainer_assignments"] == []
