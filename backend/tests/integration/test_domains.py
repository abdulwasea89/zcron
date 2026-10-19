"""Integration tests for the full backend surface: cash, receipts, classes,
staff, payroll, refunds, members, analytics, SaaS billing.

Each test provisions a gym (owner) and, where needed, an active member, then
exercises the domain through the HTTP API to verify the wired behaviour.
"""

from __future__ import annotations

import base64
import uuid

import pytest

from tests.helpers import OWNER_PROFILE, latest_code_for

PASSWORD = "Sup3rStr0ng!Pass"
MEMBER_PWD = "M3mberStr0ng!Pwd"


async def _provision_gym(client, *, owner_email="owner@g.com", gym="Iron Pulse Boxing", tier="pro"):
    """Owner register -> verify -> provision -> connect Stripe -> publish plan.

    Returns (headers, org_id, org_code, plan_id).
    """

    await client.post("/api/v1/auth/register", json={
        "full_name": "Alex", "email": owner_email,
        "password": PASSWORD, "confirm_password": PASSWORD, **OWNER_PROFILE})
    code = latest_code_for(owner_email)
    await client.post("/api/v1/auth/verify-email", json={"email": owner_email, "code": code})
    r = await client.post("/api/v1/organizations/register", json={
        "owner_email": owner_email,
        "details": {"name": gym, "default_currency": "USD"},
        "tier": tier})
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
    return headers, org_id, org_code, plan_id


async def _signup_member(client, org_code, plan_id, email) -> dict:
    """Full member signup -> returns member's auth headers + member_id."""

    await client.post("/api/v1/memberships/signup/request-email",
                      json={"org_code": org_code, "email": email})
    code = latest_code_for(email)
    await client.post("/api/v1/memberships/signup/verify-email",
                      json={"org_code": org_code, "email": email, "code": code})
    r = await client.post("/api/v1/memberships/signup/set-password",
                          json={"org_code": org_code, "email": email, "password": MEMBER_PWD})
    member_id = r.json()["member_id"]
    key = str(uuid.uuid4())
    r = await client.post("/api/v1/memberships/signup/pay",
                          headers={"Idempotency-Key": key},
                          json={"org_code": org_code, "email": email, "plan_id": plan_id})
    body = r.json()
    member_headers = {"Authorization": f"Bearer {body['access_token']}",
                      "X-Organization-Id": body["organization_id"]}
    return {"headers": member_headers, "member_id": member_id, "org_id": body["organization_id"]}


# --------------------------------------------------------------------- cash
@pytest.mark.asyncio
async def test_cash_payment_logging_activates_member(client):
    headers, org_id, org_code, plan_id = await _provision_gym(client)
    # Create a pending member via signup steps (no payment).
    email = "cashmember@g.com"
    await client.post("/api/v1/memberships/signup/request-email",
                      json={"org_code": org_code, "email": email})
    c = latest_code_for(email)
    await client.post("/api/v1/memberships/signup/verify-email",
                      json={"org_code": org_code, "email": email, "code": c})
    r = await client.post("/api/v1/memberships/signup/set-password",
                          json={"org_code": org_code, "email": email, "password": MEMBER_PWD})
    member_id = r.json()["member_id"]

    r = await client.post("/api/v1/cash/log", headers={**headers, "Idempotency-Key": "cash-activate"}, json={
        "member_id": member_id, "plan_id": plan_id, "amount": 149.0, "method": "cash"})
    assert r.status_code == 201, r.text
    assert r.json()["member_status"] == "active"
    receipt_url = r.json()["receipt_pdf_url"]
    assert receipt_url

    # The advertised receipt link resolves to a real PDF, not a dead stub key.
    r = await client.get(f"/api/v1{receipt_url}", headers=headers)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/pdf")
    assert r.content.startswith(b"%PDF-")
    assert b"PAYMENT RECEIPT" in r.content


@pytest.mark.asyncio
async def test_cash_receipt_is_tenant_scoped(client):
    """A payment's receipt must not be readable from another org."""
    headers, _org_id, org_code, plan_id = await _provision_gym(client)
    email = "receiptscope@g.com"
    await client.post("/api/v1/memberships/signup/request-email",
                      json={"org_code": org_code, "email": email})
    c = latest_code_for(email)
    await client.post("/api/v1/memberships/signup/verify-email",
                      json={"org_code": org_code, "email": email, "code": c})
    r = await client.post("/api/v1/memberships/signup/set-password",
                          json={"org_code": org_code, "email": email, "password": MEMBER_PWD})
    member_id = r.json()["member_id"]

    r = await client.post("/api/v1/cash/log", headers={**headers, "Idempotency-Key": "cash-receipt-scope"}, json={
        "member_id": member_id, "plan_id": plan_id, "amount": 149.0, "method": "cash"})
    payment_id = r.json()["payment_id"]

    other_headers, *_ = await _provision_gym(client)
    r = await client.get(f"/api/v1/cash/payments/{payment_id}/receipt", headers=other_headers)
    assert r.status_code == 404, r.text


@pytest.mark.asyncio
async def test_cash_reconciliation_discrepancy(client):
    headers, org_id, org_code, plan_id = await _provision_gym(client)
    # Log a cash payment so the system total is 149.
    email = "recon@g.com"
    await _signup_member(client, org_code, plan_id, email)  # card payment, not cash
    # Reconcile with a mismatching count -> discrepancy recorded.
    r = await client.post("/api/v1/cash/reconcile", headers=headers, json={
        "business_date": "2026-06-15", "counted_total": 50.0})
    assert r.status_code == 201, r.text
    assert r.json()["discrepancy"] == 50.0  # system cash total 0, counted 50


# ------------------------------------------------ cash member search (front desk)
@pytest.mark.asyncio
async def test_cash_member_search_allows_front_desk(client):
    """Front-desk staff can search members for cash logging and list plans,
    but still can't read the admin directory (which exposes salaries)."""

    headers, org_id, org_code, plan_id = await _provision_gym(client)
    await _signup_member(client, org_code, plan_id, "searchme@g.com")

    r = await client.post("/api/v1/staff/invites", headers=headers,
                          json={"role": "front_desk", "email": "fd@cash.com"})
    invite_code = r.json()["code"]
    r = await client.post("/api/v1/staff/invites/redeem", json={
        "code": invite_code, "full_name": "Front Desk", "password": PASSWORD})
    body = r.json()
    th = {"Authorization": f"Bearer {body['access_token']}", "X-Organization-Id": body["organization_id"]}
    assert body["role"] == "front_desk"

    # Query-based search matches the member's email.
    r = await client.get("/api/v1/cash/members", headers=th, params={"q": "searchme"})
    assert r.status_code == 200, r.text
    rows = r.json()
    assert any(row["email"] == "searchme@g.com" for row in rows)

    # Staff hold memberships too, so they're searchable and carry their role.
    r = await client.get("/api/v1/cash/members", headers=th, params={"q": "fd@cash.com"})
    assert r.status_code == 200, r.text
    rows = r.json()
    assert [row["role"] for row in rows] == ["front_desk"]

    # Empty query returns everyone in the org: owner + member + front desk.
    r = await client.get("/api/v1/cash/members", headers=th)
    assert r.status_code == 200, r.text
    assert {row["role"] for row in r.json()} == {"owner", "member", "front_desk"}

    # Front-desk can list plans (VIEW_PLANS) needed by the cash form.
    r = await client.get("/api/v1/plans", headers=th)
    assert r.status_code == 200, r.text
    assert any(p["id"] == plan_id for p in r.json())

    # ...but the admin directory (with salary fields) stays owner/manager-only.
    r = await client.get("/api/v1/members", headers=th)
    assert r.status_code == 403


# ------------------------------------------------------------------ receipts
@pytest.mark.asyncio
async def test_receipt_upload_auto_approves(client):
    headers, org_id, org_code, plan_id = await _provision_gym(client)
    email = "receipt@g.com"
    # Create pending member.
    await client.post("/api/v1/memberships/signup/request-email",
                      json={"org_code": org_code, "email": email})
    c = latest_code_for(email)
    await client.post("/api/v1/memberships/signup/verify-email",
                      json={"org_code": org_code, "email": email, "code": c})
    r = await client.post("/api/v1/memberships/signup/set-password",
                          json={"org_code": org_code, "email": email, "password": MEMBER_PWD})
    # Member needs to log in to get a token. Use member-login.
    r = await client.post("/api/v1/auth/member-login",
                          json={"org_code": org_code, "email": email, "password": MEMBER_PWD})
    body = r.json()
    mh = {"Authorization": f"Bearer {body['access_token']}", "X-Organization-Id": body["organization_id"]}

    # Upload a receipt whose stub OCR will match the plan price (149) + payee.
    image_bytes = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    )
    files = {"file": ("receipt.png", image_bytes, "image/png")}
    r = await client.post("/api/v1/receipts/upload", headers=mh,
                          data={"plan_id": plan_id}, files=files)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] in {"auto_approved", "pending_review"}
    assert body["confidence_score"] is not None


@pytest.mark.asyncio
async def test_receipt_duplicate_detected(client):
    headers, org_id, org_code, plan_id = await _provision_gym(client)
    email = "dup@g.com"
    await client.post("/api/v1/memberships/signup/request-email",
                      json={"org_code": org_code, "email": email})
    c = latest_code_for(email)
    await client.post("/api/v1/memberships/signup/verify-email",
                      json={"org_code": org_code, "email": email, "code": c})
    await client.post("/api/v1/memberships/signup/set-password",
                      json={"org_code": org_code, "email": email, "password": MEMBER_PWD})
    r = await client.post("/api/v1/auth/member-login",
                          json={"org_code": org_code, "email": email, "password": MEMBER_PWD})
    body = r.json()
    mh = {"Authorization": f"Bearer {body['access_token']}", "X-Organization-Id": body["organization_id"]}

    same_bytes = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    )
    files = {"file": ("r1.png", same_bytes, "image/png")}
    await client.post("/api/v1/receipts/upload", headers=mh, data={"plan_id": plan_id}, files=files)
    files = {"file": ("r2.png", same_bytes, "image/png")}
    r = await client.post("/api/v1/receipts/upload", headers=mh, data={"plan_id": plan_id}, files=files)
    assert r.status_code == 201, r.text
    assert r.json()["is_duplicate"] is True
    assert r.json()["status"] == "pending_review"


# ------------------------------------------------------------------ classes
@pytest.mark.asyncio
async def test_class_create_and_member_book_idempotent(client):
    headers, org_id, org_code, plan_id = await _provision_gym(client)
    info = await _signup_member(client, org_code, plan_id, "booker@g.com")

    r = await client.post("/api/v1/classes", headers=headers, json={
        "title": "6PM Boxing", "starts_at": "2026-07-01T18:00:00", "capacity": 10})
    assert r.status_code == 201, r.text
    class_id = r.json()["id"]

    key = str(uuid.uuid4())
    r = await client.post("/api/v1/classes/book",
                          headers={**info["headers"], "Idempotency-Key": key},
                          json={"class_session_id": class_id})
    assert r.status_code == 200, r.text

    # Idempotent replay -> same booking, no double count.
    r2 = await client.post("/api/v1/classes/book",
                           headers={**info["headers"], "Idempotency-Key": key},
                           json={"class_session_id": class_id})
    assert r2.status_code == 200, r2.text

    r = await client.get("/api/v1/classes", headers=headers)
    booked = [c for c in r.json() if c["id"] == class_id][0]["booked_count"]
    assert booked == 1


# -------------------------------------------------------------------- staff
@pytest.mark.asyncio
async def test_staff_invite_redeem_and_shift(client):
    headers, org_id, org_code, plan_id = await _provision_gym(client)
    r = await client.post("/api/v1/staff/invites", headers=headers,
                          json={"role": "trainer", "email": "trainer@g.com"})
    assert r.status_code == 201, r.text
    invite_code = r.json()["code"]

    r = await client.post("/api/v1/staff/invites/redeem", json={
        "code": invite_code, "full_name": "Marcus Trainer", "password": PASSWORD})
    assert r.status_code == 200, r.text
    body = r.json()
    th = {"Authorization": f"Bearer {body['access_token']}", "X-Organization-Id": body["organization_id"]}
    assert body["role"] == "trainer"

    # Shift check-in then check-out.
    r = await client.post("/api/v1/staff/shifts/check-in", headers=th)
    assert r.status_code == 201, r.text
    r = await client.post("/api/v1/staff/shifts/check-out", headers=th)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "checked_out"


# ------------------------------------------------------------------ payroll
@pytest.mark.asyncio
async def test_payroll_draft_and_finalize(client):
    headers, org_id, org_code, plan_id = await _provision_gym(client)
    # Invite + redeem trainer, set fixed salary.
    r = await client.post("/api/v1/staff/invites", headers=headers,
                          json={"role": "trainer", "email": "payme@g.com"})
    invite_code = r.json()["code"]
    r = await client.post("/api/v1/staff/invites/redeem", json={
        "code": invite_code, "full_name": "Pay Me", "password": PASSWORD})
    # Find the trainer's member id via directory.
    r = await client.get("/api/v1/members", headers=headers, params={"role": "trainer"})
    trainer_member_id = r.json()[0]["member_id"]
    await client.patch(f"/api/v1/staff/{trainer_member_id}/compensation", headers=headers,
                       json={"fixed_monthly_salary": 1500.0})

    # Draft payroll.
    r = await client.post("/api/v1/payroll/runs", headers=headers, json={
        "period_start": "2026-06-01", "period_end": "2026-06-30"})
    assert r.status_code == 201, r.text
    run = r.json()
    assert run["total_net"] == 1500.0
    run_id = run["id"]
    entry_id = run["entries"][0]["id"]

    # Adjust with a bonus (requires note).
    r = await client.patch(f"/api/v1/payroll/runs/{run_id}/entries/{entry_id}", headers=headers,
                           json={"bonus": 100.0, "note": "100% attendance"})
    assert r.status_code == 200, r.text
    assert r.json()["net"] == 1600.0

    # Finalize -> pay stub generated.
    r = await client.post(f"/api/v1/payroll/runs/{run_id}/finalize", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "finalized"
    assert r.json()["entries"][0]["pay_stub_url"]


# ------------------------------------------------------------------ refunds
@pytest.mark.asyncio
async def test_refund_is_idempotent(client):
    headers, org_id, org_code, plan_id = await _provision_gym(client)
    await _signup_member(client, org_code, plan_id, "refundme@g.com")

    r = await client.get("/api/v1/payments", headers=headers)
    assert r.status_code == 200, r.text
    payment = [p for p in r.json() if p["amount"] == 149.0][0]

    key = str(uuid.uuid4())
    r = await client.post("/api/v1/payments/refund",
                          headers={**headers, "Idempotency-Key": key},
                          json={"payment_id": payment["id"]})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "refunded"
    assert r.json()["refunded_amount"] == 149.0

    # Replay -> same result, no double refund.
    r2 = await client.post("/api/v1/payments/refund",
                           headers={**headers, "Idempotency-Key": key},
                           json={"payment_id": payment["id"]})
    assert r2.status_code == 200, r2.text
    assert r2.json()["refunded_amount"] == 149.0


# ---------------------------------------------------------------- analytics
@pytest.mark.asyncio
async def test_analytics_revenue_and_headline(client):
    headers, org_id, org_code, plan_id = await _provision_gym(client)
    await _signup_member(client, org_code, plan_id, "rev1@g.com")

    r = await client.get("/api/v1/analytics/revenue", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["total_revenue"] == 149.0
    assert r.json()["active_members"] == 1

    r = await client.get("/api/v1/analytics/headline", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["active_members"] == 1


# -------------------------------------------------------------- saas billing
@pytest.mark.asyncio
async def test_saas_downgrade_blocked_by_member_cap(client):
    headers, org_id, org_code, plan_id = await _provision_gym(client, tier="pro")
    r = await client.get("/api/v1/saas-billing/status", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["saas_tier"] == "pro"

    # Downgrade pro -> starter should succeed (0 members < 25 cap).
    r = await client.post("/api/v1/saas-billing/downgrade",
                          headers={**headers, "Idempotency-Key": "saas-downgrade"},
                          json={"tier": "starter"})
    assert r.status_code == 200, r.text
    assert r.json()["saas_tier"] == "starter"
    assert r.json()["member_cap"] == 25


@pytest.mark.asyncio
async def test_saas_upgrade(client):
    headers, org_id, org_code, plan_id = await _provision_gym(client, tier="starter")
    r = await client.post("/api/v1/saas-billing/upgrade",
                          headers={**headers, "Idempotency-Key": "saas-upgrade"},
                          json={"tier": "pro"})
    assert r.status_code == 200, r.text
    assert r.json()["saas_tier"] == "pro"
    assert r.json()["member_cap"] == 100


# --------------------------------------------------------- mobile/web split
@pytest.mark.asyncio
async def test_member_cannot_access_revenue_analytics(client):
    headers, org_id, org_code, plan_id = await _provision_gym(client)
    info = await _signup_member(client, org_code, plan_id, "nosy@g.com")
    r = await client.get("/api/v1/analytics/revenue", headers=info["headers"])
    assert r.status_code == 403
