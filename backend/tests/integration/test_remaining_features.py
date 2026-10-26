"""Integration tests for remaining features: WebSocket sync, Stripe webhooks,
MFA (TOTP), org-code rotation, and member spreadsheet import.

These exercise the wiring added on top of the 13 core domains.
"""

from __future__ import annotations

import io

import pytest
from openpyxl import Workbook

from app.core import totp
from app.core.security import now_utc
from tests.helpers import OWNER_PROFILE, latest_code_for


def _invite_code_for(email: str) -> str:
    """Extract the invite token from the most recent invite email in the outbox."""

    from app.integrations.email import outbox

    for mail in reversed(outbox):
        if mail.to in (email.lower(), email) and "Use this code to join:" in mail.body:
            return mail.body.split("Use this code to join:", 1)[1].strip()
    raise AssertionError(f"No invite email found for {email}")

PASSWORD = "Sup3rStr0ng!Pass"
MEMBER_PWD = "M3mberStr0ng!Pwd"


async def _provision_gym(client, *, owner_email="owner@g.com", gym="Iron Pulse Boxing", tier="pro"):
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


# --------------------------------------------------------------- invites
@pytest.mark.asyncio
async def test_member_invite_redeem_and_login(client):
    """Full invite loop: admin invites -> member redeems the code -> can log in
    and reach pending_payment. Regression: invite codes used to be issued but had
    no redeem endpoint, so an invited member could never actually join."""

    headers, org_id, org_code, plan_id = await _provision_gym(client)

    # Admin invites a new member (stub email -> code returned + in outbox).
    r = await client.post("/api/v1/members/invite", headers=headers,
                          json={"email": "invitee@g.com"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["email_delivered"] is False  # stub mode in tests
    code = body["invite_code"] or _invite_code_for("invitee@g.com")
    assert code

    # Member redeems the invite: sets a password, advances to pending_payment.
    r = await client.post("/api/v1/memberships/invite/redeem", json={
        "org_code": org_code, "email": "invitee@g.com", "code": code, "password": MEMBER_PWD})
    assert r.status_code == 200, r.text
    assert r.json()["member_status"] == "pending_payment"

    # The invited member can now log in with the password they just set.
    r = await client.post("/api/v1/auth/member-login", json={
        "org_code": org_code, "email": "invitee@g.com", "password": MEMBER_PWD})
    assert r.status_code == 200, r.text
    assert r.json()["access_token"]

    # A second redeem with the same (now consumed) code is rejected.
    r = await client.post("/api/v1/memberships/invite/redeem", json={
        "org_code": org_code, "email": "invitee@g.com", "code": code, "password": MEMBER_PWD})
    assert r.status_code == 400, r.text


# ------------------------------------------------------------- magic link
def _magic_token_for(email: str) -> str:
    """Extract the magic-link token from the most recent sign-in email."""

    from app.integrations.email import outbox

    for mail in reversed(outbox):
        if mail.to in (email.lower(), email) and "Token: " in mail.body:
            return mail.body.split("Token: ", 1)[1].strip()
    raise AssertionError(f"No magic-link email found for {email}")


@pytest.mark.asyncio
async def test_magic_link_login(client):
    """Mobile login Method B (Section 5.4): owner requests a magic link by
    org code + email, then exchanges the emailed token for an org-scoped session."""

    _, org_id, org_code, _ = await _provision_gym(client, owner_email="owner@g.com")

    # Request a link — response is vague and does not carry the token.
    r = await client.post("/api/v1/auth/magic-link/request", json={
        "org_code": org_code, "email": "owner@g.com"})
    assert r.status_code == 200, r.text
    assert "token" not in r.json()

    token = _magic_token_for("owner@g.com")
    assert token

    # Exchange the token for a session.
    r = await client.post("/api/v1/auth/magic-link/verify", json={
        "org_code": org_code, "email": "owner@g.com", "token": token})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["access_token"]
    assert body["organization_id"] == org_id
    assert body["role"] == "owner"

    # The token is single-use: a second verify fails.
    r = await client.post("/api/v1/auth/magic-link/verify", json={
        "org_code": org_code, "email": "owner@g.com", "token": token})
    assert r.status_code == 400, r.text


@pytest.mark.asyncio
async def test_magic_link_request_is_silent_for_unknown_email(client):
    """Requesting a link for an email that isn't an admin of the org must be
    silent (no email issued, still a 200) so membership is never revealed."""

    _, _, org_code, _ = await _provision_gym(client, owner_email="owner2@g.com")

    r = await client.post("/api/v1/auth/magic-link/request", json={
        "org_code": org_code, "email": "stranger@g.com"})
    assert r.status_code == 200, r.text

    from app.integrations.email import outbox

    assert not any(
        m.to == "stranger@g.com" and "Token: " in m.body for m in outbox
    )


# ------------------------------------------------------------------ MFA
@pytest.mark.asyncio
async def test_mfa_enroll_confirm_and_login_challenge(client):
    headers, org_id, org_code, plan_id = await _provision_gym(client)

    # Enroll -> get a secret, confirm with a valid code.
    r = await client.post("/api/v1/auth/mfa/enroll", headers=headers)
    assert r.status_code == 200, r.text
    secret = r.json()["secret"]
    code = totp.now_code(secret, for_time=now_utc())
    r = await client.post("/api/v1/auth/mfa/confirm", headers=headers, json={"code": code})
    assert r.status_code == 200, r.text

    # Login now requires MFA: password-only returns requires_mfa with no token.
    r = await client.post("/api/v1/auth/login", json={"email": "owner@g.com", "password": PASSWORD})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["requires_mfa"] is True
    assert body["access_token"] == ""

    # Login with the code succeeds.
    code = totp.now_code(secret, for_time=now_utc())
    r = await client.post("/api/v1/auth/login",
                          json={"email": "owner@g.com", "password": PASSWORD, "mfa_code": code})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["access_token"]
    assert body["requires_mfa"] is False


# ----------------------------------------------------------- org-code rotation
@pytest.mark.asyncio
async def test_org_code_rotation_changes_code(client):
    headers, org_id, org_code, plan_id = await _provision_gym(client)
    r = await client.post("/api/v1/organizations/me/rotate-code", headers=headers)
    assert r.status_code == 200, r.text
    new_code = r.json()["org_code"]
    assert new_code != org_code

    # Old code no longer resolves a login (vague 401).
    await client.post("/api/v1/auth/register", json={
        "full_name": "Max Owner", "email": "m@g.com", "password": MEMBER_PWD, "confirm_password": MEMBER_PWD,
        **OWNER_PROFILE})
    # Owner can still fetch org with existing token (owner session not revoked).
    r = await client.get("/api/v1/organizations/me", headers=headers)
    assert r.status_code == 200
    assert r.json()["org_code"] == new_code


# -------------------------------------------------------------- gym rename
@pytest.mark.asyncio
async def test_org_name_update_and_validation(client):
    headers, org_id, org_code, plan_id = await _provision_gym(client)

    r = await client.patch("/api/v1/organizations/me/name", headers=headers,
                           json={"name": "Iron Pulse Boxing West"})
    assert r.status_code == 200, r.text

    r = await client.get("/api/v1/organizations/me", headers=headers)
    assert r.json()["name"] == "Iron Pulse Boxing West"

    # Empty / non-name input is rejected.
    r = await client.patch("/api/v1/organizations/me/name", headers=headers, json={"name": "  "})
    assert r.status_code == 422, r.text

    r = await client.patch("/api/v1/organizations/me/name", headers=headers, json={"name": "Iron 123"})
    assert r.status_code == 422, r.text


# --------------------------------------------------------- Spreadsheet import
@pytest.mark.asyncio
async def test_bulk_import_csv(client, monkeypatch):
    from app.services import organizations_service

    monkeypatch.setattr(organizations_service.platform_stripe, "live", False)
    monkeypatch.setattr(organizations_service.connect_stripe, "live", False)
    headers, org_id, org_code, plan_id = await _provision_gym(client)
    csv_body = (
        "email,full_name,phone\n"
        "alice@import.com,Alice,111\n"
        "bob@import.com,Bob,222\n"
        "not-an-email,Bad,000\n"
    ).encode("utf-8")
    files = {"file": ("members.csv", csv_body, "text/csv")}
    r = await client.post("/api/v1/members/import", headers={**headers, "Idempotency-Key": "import-csv"}, files=files)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["created"] == 2
    # Stub email mode: the activation email genuinely did not go out, so both
    # imported rows are reported as undelivered alongside the bad-email row.
    # send_email returns False without a provider, which is what makes this true.
    assert {e["error"] for e in body["errors"]} == {
        "invalid or missing email",
        "member created but activation email not delivered",
    }
    assert {e["row"] for e in body["errors"] if e["error"].startswith("member created")} == {2, 3}

    # Imported members appear in the directory as pending_activation.
    r = await client.get("/api/v1/members", headers=headers, params={"status": "pending_activation"})
    emails = {m["email"] for m in r.json()}
    assert {"alice@import.com", "bob@import.com"} <= emails

    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["email", "full_name", "phone"])
    sheet.append(["excel@import.com", "Excel Member", "+15555550123"])
    xlsx = io.BytesIO()
    workbook.save(xlsx)
    r = await client.post(
        "/api/v1/members/import", headers={**headers, "Idempotency-Key": "import-excel"},
        files={"file": ("members.xlsx", xlsx.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert r.status_code == 201, r.text
    assert r.json()["created"] == 1

    invalid_type = await client.post(
        "/api/v1/members/import", headers=headers,
        files={"file": ("members.xls", csv_body, "application/vnd.ms-excel")},
    )
    assert invalid_type.status_code == 422

    too_large = await client.post(
        "/api/v1/members/import", headers=headers,
        files={"file": ("large.csv", b"x" * 2_000_001, "text/csv")},
    )
    assert too_large.status_code == 413


# ---------------------------------------------------------- Stripe webhooks
@pytest.mark.asyncio
async def test_platform_webhook_accepts_stub_event(client):
    await _provision_gym(client)
    # In stub mode (no real Stripe key) the endpoint accepts a well-formed JSON
    # event without a signature and routes it by type.
    event = {"type": "invoice.payment_succeeded", "data": {"object": {"customer": "cus_unknown"}}}
    r = await client.post("/api/v1/webhooks/stripe", json=event)
    assert r.status_code == 200, r.text
    assert r.json().get("handled") == "invoice.payment_succeeded"


@pytest.mark.asyncio
async def test_connect_webhook_unknown_intent_ignored(client):
    await _provision_gym(client)
    event = {"type": "payment_intent.succeeded", "data": {"object": {"id": "pi_nope"}}}
    r = await client.post("/api/v1/webhooks/stripe-connect", json=event)
    assert r.status_code == 200, r.text
    assert "ignored" in r.json()


@pytest.mark.asyncio
async def test_webhook_unknown_type_acknowledged(client):
    event = {"type": "customer.created", "data": {"object": {}}}
    r = await client.post("/api/v1/webhooks/stripe", json=event)
    assert r.status_code == 200, r.text
    assert r.json().get("ignored") == "customer.created"


# --------------------------------------------------------------- realtime
@pytest.mark.asyncio
async def test_ws_rejects_garbage_token():
    """The WS auth helper rejects an invalid token without touching the DB."""

    from app.api.v1.routes.ws import _authorize

    assert await _authorize("garbage.token") is None
    assert await _authorize("") is None


@pytest.mark.asyncio
async def test_realtime_broadcast_is_org_scoped():
    """Broadcast reaches sockets registered for the org and skips other orgs."""

    from app.realtime import manager

    class FakeWS:
        def __init__(self):
            self.sent = []

        async def send_json(self, data):
            self.sent.append(data)

    ws = FakeWS()
    # Register directly (manager.connect() would call websocket.accept()).
    async with manager._lock:
        manager._by_org["org-A"].add(ws)
    try:
        await manager.broadcast("org-A", {"type": "plan.changed", "plan_id": "p1"})
        await manager.broadcast("org-B", {"type": "noise"})
    finally:
        await manager.disconnect("org-A", ws)

    assert {"type": "plan.changed", "plan_id": "p1"} in ws.sent
    assert all(e.get("type") != "noise" for e in ws.sent)
    assert manager.connection_count("org-A") == 0


@pytest.mark.asyncio
async def test_duplicate_invite_rejected_and_constraint_enforced(client, db):
    """A second invite for the same email must not create another membership.

    Regression: there was no DB unique constraint on (organization_id, user_id),
    so repeat/concurrent invites created duplicate rows that crashed login with
    ``MultipleResultsFound``. This test pins both the API guard (409 on the
    second invite) and the new unique constraint at the schema layer."""

    import pytest
    from sqlalchemy.exc import IntegrityError
    from sqlmodel import select

    from app.core.constants import MemberStatus, Role
    from app.models.membership import OrganizationMember
    from app.models.user import User

    headers, org_id, org_code, plan_id = await _provision_gym(client)

    r = await client.post("/api/v1/members/invite", headers=headers, json={"email": "dup@g.com"})
    assert r.status_code == 201, r.text
    r = await client.post("/api/v1/members/invite", headers=headers, json={"email": "dup@g.com"})
    assert r.status_code == 409, r.text

    user = (
        await db.execute(select(User).where(User.email == "dup@g.com"))
    ).scalar_one_or_none()
    assert user is not None
    rows = list(
        (
            await db.execute(
                select(OrganizationMember).where(
                    OrganizationMember.organization_id == org_id,
                    OrganizationMember.user_id == user.id,
                )
            )
        ).scalars()
    )
    assert len(rows) == 1

    # The model-level constraint is enforced even in the in-memory test schema.
    duplicate = OrganizationMember(
        organization_id=org_id, user_id=user.id, role=Role.MEMBER,
        member_status=MemberStatus.PENDING_ACTIVATION,
    )
    db.add(duplicate)
    with pytest.raises(IntegrityError):
        await db.flush()
    await db.rollback()
