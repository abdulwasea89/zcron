"""Integration tests for the office vertical (B2B invoicing + seat-holders).

Provision an office org -> publish a space plan -> add a company -> sign a seat
contract (auto-drafts the first invoice) -> invite + redeem a seat-holder (to
ACTIVE, no payment) -> send + settle the invoice (idempotent) -> headline KPIs.
Plus cross-industry isolation and the invite-only signup guard.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from tests.helpers import OWNER_PROFILE, latest_code_for

PASSWORD = "Sup3rStr0ng!Pass"
SEAT_PWD = "S3atStr0ng!Pwd"


async def _provision_office(client, *, owner_email="office.owner@g.com", name="Acme Suites", tier="pro"):
    """Owner register (industry=office) -> publish a published space plan.

    Returns (headers, org_id, org_code, plan_id). Offices need no Stripe Connect.
    """

    await client.post("/api/v1/auth/register", json={
        "full_name": "Opal", "email": owner_email,
        "password": PASSWORD, "confirm_password": PASSWORD, **OWNER_PROFILE})
    code = latest_code_for(owner_email)
    await client.post("/api/v1/auth/verify-email", json={"email": owner_email, "code": code})
    r = await client.post("/api/v1/organizations/register", json={
        "owner_email": owner_email,
        "details": {"name": name, "industry": "office", "default_currency": "USD"},
        "tier": tier})
    body = r.json()
    org_id = body["organization"]["id"]
    org_code = body["organization"]["org_code"]
    assert body["organization"]["industry"] == "office"
    headers = {"Authorization": f"Bearer {body['access_token']}", "X-Organization-Id": org_id}

    # Published space plan: per-seat per-term price, monthly billing to a company.
    r = await client.post("/api/v1/plans", headers=headers, json={
        "name": "Fixed Desk", "price": 250.0,
        "spec": {"space_type": "fixed_desk", "term": "monthly",
                 "billing": "company_invoice", "room_credits": 5},
    })
    assert r.status_code == 201, r.text
    plan_id = r.json()["id"]
    await client.post(f"/api/v1/plans/{plan_id}/publish", headers=headers)
    return headers, org_id, org_code, plan_id


async def _add_company_and_contract(client, headers, plan_id, *, company="Northwind Ltd",
                                    seats=3, billing_email="ap@northwind.com") -> dict:
    r = await client.post("/api/v1/companies", headers=headers, json={
        "name": company, "billing_email": billing_email, "contact_email": billing_email})
    assert r.status_code == 201, r.text
    company_id = r.json()["id"]

    r = await client.post(f"/api/v1/companies/{company_id}/contracts", headers=headers, json={
        "plan_id": plan_id, "seats": seats})
    assert r.status_code == 201, r.text
    contract = r.json()
    assert contract["seats"] == seats
    assert contract["price_per_seat"] == 250.0
    assert contract["term"] == "monthly"
    assert contract["status"] == "active"
    return {"company_id": company_id, "contract_id": contract["id"], "contract": contract}


async def _invite_under(client, headers, org_code, company_id, email, password=SEAT_PWD) -> dict:
    r = await client.post(f"/api/v1/companies/{company_id}/seat-holders", headers=headers,
                          json={"email": email})
    assert r.status_code == 201, r.text
    body = r.json()
    member_id = body["member_id"]
    invite_code = body["invite_code"]  # stub email mode exposes the code
    assert invite_code, "expected invite code in stub email mode"

    r = await client.post("/api/v1/memberships/invite/redeem", json={
        "org_code": org_code, "email": email, "code": invite_code, "password": password})
    assert r.status_code == 200, r.text
    assert r.json()["member_status"] == "active"

    r = await client.post("/api/v1/auth/member-login",
                          json={"org_code": org_code, "email": email, "password": password})
    body = r.json()
    member_headers = {"Authorization": f"Bearer {body['access_token']}",
                      "X-Organization-Id": body["organization_id"]}
    return {"member_id": member_id, "headers": member_headers, "member_status": "active"}


# ------------------------------------------------------------------- core flow
@pytest.mark.asyncio
async def test_office_company_contract_seat_holder_and_invoice(client):
    headers, org_id, org_code, plan_id = await _provision_office(client)
    setup = await _add_company_and_contract(client, headers, plan_id)
    company_id = setup["company_id"]
    contract_id = setup["contract_id"]

    # First invoice auto-drafted at contract signing: 3 seats x $250.
    r = await client.get("/api/v1/invoices", headers=headers)
    assert r.status_code == 200, r.text
    invoices = r.json()
    assert len(invoices) == 1
    inv = invoices[0]
    assert inv["status"] == "draft"
    assert inv["total"] == 750.0
    assert inv["invoice_number"].startswith("INV-")
    assert inv["company_name"] == "Northwind Ltd"

    # Company detail exposes capacity + the seat-holder roster.
    r = await client.get(f"/api/v1/companies/{company_id}", headers=headers)
    assert r.status_code == 200, r.text
    assert len(r.json()["contracts"]) == 1

    # Invite + redeem a seat-holder -> ACTIVE with no payment step.
    holder = await _invite_under(client, headers, org_code, company_id, "holder1@g.com")
    holder_headers = holder["headers"]

    # A seat-holder (member) sees the company's own dues only (self-service).
    # Draft invoices are not "due", so the list is empty until sent.
    r = await client.get("/api/v1/invoices/my-company", headers=holder_headers)
    assert r.status_code == 200, r.text
    assert r.json() == []

    # Occupancy reflects the redeemed seat-holder.
    r = await client.get("/api/v1/companies", headers=headers)
    row = [c for c in r.json() if c["id"] == company_id][0]
    assert row["seat_capacity"] == 3
    assert row["occupied_seats"] == 1

    # Send the invoice (company billing email present) -> now "due" for the holder.
    r = await client.post(f"/api/v1/invoices/{inv['id']}/send", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "sent"
    r = await client.get("/api/v1/invoices/my-company", headers=holder_headers)
    assert r.status_code == 200, r.text
    assert len(r.json()) == 1
    assert r.json()[0]["id"] == inv["id"]

    # Settle offline, idempotently: same key twice -> one Payment(kind=space).
    key = str(uuid.uuid4())
    r = await client.post(f"/api/v1/invoices/{inv['id']}/record-payment",
                          headers={**headers, "Idempotency-Key": key},
                          json={"method": "bank_transfer", "note": "Wire 001"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "paid"
    assert r.json()["paid_amount"] == 750.0
    # replay
    r2 = await client.post(f"/api/v1/invoices/{inv['id']}/record-payment",
                           headers={**headers, "Idempotency-Key": key},
                           json={"method": "bank_transfer"})
    assert r2.status_code == 200, r2.text

    r = await client.get(f"/api/v1/invoices/{inv['id']}/payments", headers=headers)
    assert len(r.json()) == 1
    assert r.json()[0]["amount"] == 750.0

    # Renewal: once the open invoice is settled, issuing the next term works.
    r = await client.post("/api/v1/invoices/issue", headers=headers,
                          json={"contract_id": contract_id})
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "draft"
    assert r.json()["total"] == 750.0


# ------------------------------------------------------------------- invoice template
@pytest.mark.asyncio
async def test_office_invoice_settings_persist_and_flip_checklist(client):
    headers, org_id, org_code, plan_id = await _provision_office(client)

    # PUT persists each template field onto its Organization column.
    r = await client.put("/api/v1/organizations/me/invoice-settings", headers=headers, json={
        "legal_name": "Acme Suites LLC",
        "address": "1 Market St, Springfield",
        "tax_id": "US-12-3456789",
        "payment_terms_days": 14,
    })
    assert r.status_code == 200, r.text
    assert r.json() == {
        "legal_name": "Acme Suites LLC",
        "address": "1 Market St, Springfield",
        "tax_id": "US-12-3456789",
        "payment_terms_days": 14,
    }

    # Round-trip through a fresh read proves the columns actually persisted.
    r = await client.get("/api/v1/organizations/me/invoice-settings", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["legal_name"] == "Acme Suites LLC"
    assert r.json()["payment_terms_days"] == 14

    # Partial PUT is a legal merge (updates only the sent field).
    r = await client.put("/api/v1/organizations/me/invoice-settings", headers=headers,
                         json={"tax_id": "EU-XX-000"})
    assert r.status_code == 200, r.text
    assert r.json()["tax_id"] == "EU-XX-000"
    assert r.json()["legal_name"] == "Acme Suites LLC"  # untouched

    # Setting the template completes the office 'invoices' checklist step.
    r = await client.get("/api/v1/organizations/me/checklist", headers=headers)
    step = [s for s in r.json()["steps"] if s["code"] == "invoices"][0]
    assert step["done"] is True


# ------------------------------------------------------------------- headline KPIs
@pytest.mark.asyncio
async def test_office_headline_metrics(client):
    headers, org_id, org_code, plan_id = await _provision_office(client)
    setup = await _add_company_and_contract(client, headers, plan_id, seats=4)
    holder = await _invite_under(client, headers, org_code, setup["company_id"], "kpi@g.com")

    r = await client.get("/api/v1/analytics/headline", headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["occupied_seats"] == 1
    assert data["occupancy_pct"] == 25.0          # 1 of 4 seats
    assert data["space_mrr"] == 1000.0            # 4 seats x $250
    assert data["outstanding_invoices"] == 0.0    # auto-draft not yet sent
    # Gym keys must be absent from an office payload (industry-shaped).
    assert "active_members" not in data

    # Seat-holders (members) cannot read the headline (staff-only), like gym.
    r = await client.get("/api/v1/analytics/headline", headers=holder["headers"])
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_office_headline_with_an_open_invoice(client):
    """Regression: an org holding a *sent* invoice used to 500.

    The outstanding-balance branch only runs when there is at least one open
    invoice, so the zero-invoice test above never reached it.
    """

    headers, org_id, org_code, plan_id = await _provision_office(client)
    setup = await _add_company_and_contract(client, headers, plan_id, seats=2)

    # Signing the contract already drafted the first term's invoice; sending it
    # is what turns it into an "open" one.
    invoices = (
        await client.get(f"/api/v1/invoices?company_id={setup['company_id']}", headers=headers)
    ).json()
    assert len(invoices) == 1, invoices
    invoice_id, total = invoices[0]["id"], invoices[0]["total"]

    r = await client.post(f"/api/v1/invoices/{invoice_id}/send", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "sent"

    r = await client.get("/api/v1/analytics/headline", headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["outstanding_invoices"] == total
    assert data["occupied_seats"] == 0

    # Part-settling moves the balance, still through the same branch.
    r = await client.post(
        f"/api/v1/invoices/{invoice_id}/record-payment",
        headers={**headers, "Idempotency-Key": "office-open-invoice-payment"},
        json={"amount": 100.0, "method": "bank_transfer"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "partial"

    r = await client.get("/api/v1/analytics/headline", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["outstanding_invoices"] == round(total - 100.0, 2)


# ------------------------------------------------------- soft-wrapped code
@pytest.mark.asyncio
async def test_invite_code_survives_email_soft_wrap(client):
    """Regression: a code copied out of a wrapped email must still redeem.

    Invite codes are 43-char tokens, long enough that mail clients break them
    across lines. The pasted value then carries whitespace, which used to hash
    differently and surface as "Invalid or expired code."
    """

    headers, org_id, org_code, plan_id = await _provision_office(client)
    setup = await _add_company_and_contract(client, headers, plan_id, seats=2)
    company_id = setup["company_id"]

    r = await client.post(f"/api/v1/companies/{company_id}/seat-holders", headers=headers,
                          json={"email": "wrapped@g.com"})
    assert r.status_code == 201, r.text
    code = r.json()["invite_code"]
    assert code

    # Every flavour of whitespace a copy-paste can introduce is tolerated.
    mangled = f"  {code[:20]}\n\t{code[20:30]} \r\n {code[30:]}  "
    r = await client.post("/api/v1/memberships/invite/redeem", json={
        "org_code": org_code, "email": "wrapped@g.com", "code": mangled, "password": SEAT_PWD})
    assert r.status_code == 200, r.text
    assert r.json()["member_status"] == "active"

    # A genuinely wrong code is still rejected (the strip is not a bypass).
    r = await client.post("/api/v1/memberships/invite/redeem", json={
        "org_code": org_code, "email": "wrapped@g.com", "code": "not-a-real-code", "password": SEAT_PWD})
    assert r.status_code == 400, r.text


# ------------------------------------------------------------------- seat cap
@pytest.mark.asyncio
async def test_office_seat_capacity_enforced(client):
    headers, org_id, org_code, plan_id = await _provision_office(client)
    setup = await _add_company_and_contract(client, headers, plan_id, seats=1)
    company_id = setup["company_id"]

    await _invite_under(client, headers, org_code, company_id, "cap@g.com")
    # Second invite would exceed the single paid seat once the first is active.
    r = await client.post(f"/api/v1/companies/{company_id}/seat-holders", headers=headers,
                          json={"email": "cap2@g.com"})
    assert r.status_code == 409, r.text


# ------------------------------------------------------------------- office space slots
@pytest.mark.asyncio
async def test_office_space_slot_booking_idempotent(client):
    headers, org_id, org_code, plan_id = await _provision_office(client)
    setup = await _add_company_and_contract(client, headers, plan_id, seats=2)
    holder = await _invite_under(client, headers, org_code, setup["company_id"], "booker@g.com")

    # Admin creates a desk slot (reception/owner).
    r = await client.post("/api/v1/space", headers=headers, json={
        "title": "Desk 14", "starts_at": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
        "capacity": 1})
    assert r.status_code == 201, r.text
    slot_id = r.json()["id"]
    assert r.json()["category"] == "space_slot"

    # Seat-holder books it idempotently.
    key = str(uuid.uuid4())
    r = await client.post("/api/v1/space/book",
                          headers={**holder["headers"], "Idempotency-Key": key},
                          json={"slot_id": slot_id})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "booked"
    r2 = await client.post("/api/v1/space/book",
                           headers={**holder["headers"], "Idempotency-Key": key},
                           json={"slot_id": slot_id})
    assert r2.status_code == 200, r2.text

    r = await client.get("/api/v1/space", headers=headers)
    assert [s for s in r.json() if s["id"] == slot_id][0]["booked_count"] == 1
    # The holder's self-service list surfaces the booking.
    r = await client.get("/api/v1/space/my-bookings", headers=holder["headers"])
    assert r.status_code == 200, r.text
    assert len(r.json()) == 1


# ------------------------------------------------------------------- isolation
@pytest.mark.asyncio
async def test_office_cross_tenant_isolation_and_gym_denied(client):
    headers, org_id, org_code, plan_id = await _provision_office(client, owner_email="a@x.com",
                                                                 name="Org A")
    setup = await _add_company_and_contract(client, headers, plan_id)
    company_id = setup["company_id"]

    # A different office org cannot read company A.
    other, *_ = await _provision_office(client, owner_email="b@x.com", name="Org B")
    r = await client.get(f"/api/v1/companies/{company_id}", headers=other)
    assert r.status_code == 404

    # A gym org cannot create companies at all (MANAGE_COMPANIES is office-only).
    gym_headers, *_ = await _gym_provision(client)
    r = await client.post("/api/v1/companies", headers=gym_headers, json={"name": "GymCo"})
    assert r.status_code == 403
    r = await client.post("/api/v1/invoices/issue", headers=gym_headers,
                          json={"contract_id": "nope"})
    assert r.status_code == 403


# ------------------------------------------------------------------- signup guard
@pytest.mark.asyncio
async def test_office_open_enrollment_rejected(client):
    headers, org_id, org_code, plan_id = await _provision_office(client)
    # Even with a published plan + open enrollment default, self-serve signup is
    # refused: office onboarding is invite-only (B2B, no per-person payment).
    r = await client.post("/api/v1/memberships/signup/start",
                          json={"org_code": org_code, "captcha_token": ""})
    assert r.status_code == 403, r.text
    assert "invited" in r.json()["detail"].lower()


# ------------------------------------------------------------ gym helper reuse
async def _gym_provision(client, *, owner_email="gym.owner@g.com", name="Iron Gym"):
    await client.post("/api/v1/auth/register", json={
        "full_name": "Gym", "email": owner_email,
        "password": PASSWORD, "confirm_password": PASSWORD, **OWNER_PROFILE})
    code = latest_code_for(owner_email)
    await client.post("/api/v1/auth/verify-email", json={"email": owner_email, "code": code})
    r = await client.post("/api/v1/organizations/register", json={
        "owner_email": owner_email,
        "details": {"name": name, "default_currency": "USD"},
        "tier": "pro"})
    body = r.json()
    org_id = body["organization"]["id"]
    return {"Authorization": f"Bearer {body['access_token']}", "X-Organization-Id": org_id}, org_id
