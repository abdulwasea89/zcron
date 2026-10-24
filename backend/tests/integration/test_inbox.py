"""Integration tests for the shared team inbox (#20).

Covers ingest (create + dedupe + member match), listing and filters, reply
(idempotent + auto-assign), assign, status, AI draft, tenant isolation, and
capability enforcement.
"""

from __future__ import annotations

import uuid

import pytest

from app.models.membership import OrganizationMember
from tests.helpers import OWNER_PROFILE, latest_code_for

PASSWORD = "Sup3rStr0ng!Pass"
MEMBER_PWD = "M3mberStr0ng!Pwd"


async def _provision_gym(client, *, owner_email="owner@inbox.com"):
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


async def _ingest(client, headers, **overrides):
    payload = {"channel": "whatsapp", "handle": "+923001234567", "body": "Hi, do you have women-only hours?"}
    payload.update(overrides)
    return await client.post("/api/v1/inbox/conversations/ingest", headers=headers, json=payload)


# ------------------------------------------------------------------- ingest
@pytest.mark.asyncio
async def test_ingest_creates_and_lists(client):
    headers, _org_id, _code = await _provision_gym(client)
    r = await _ingest(client, headers)
    assert r.status_code == 201, r.text
    conv = r.json()
    assert conv["status"] == "open"
    assert conv["unread_count"] == 1
    assert conv["channel"] == "whatsapp"
    assert len(conv["messages"]) == 1
    assert conv["messages"][0]["direction"] == "inbound"

    r = await client.get("/api/v1/inbox/conversations", headers=headers)
    assert r.status_code == 200, r.text
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["preview"].startswith("Hi, do you have")
    assert rows[0]["unread_count"] == 1


@pytest.mark.asyncio
async def test_second_message_same_handle_appends(client):
    headers, _org_id, _code = await _provision_gym(client)
    await _ingest(client, headers, body="First")
    r = await _ingest(client, headers, body="Second")
    assert r.status_code == 201, r.text
    conv = r.json()
    assert len(conv["messages"]) == 2
    assert conv["unread_count"] == 2

    r = await client.get("/api/v1/inbox/conversations", headers=headers)
    assert len(r.json()) == 1  # still one thread


@pytest.mark.asyncio
async def test_external_id_is_idempotent(client):
    headers, _org_id, _code = await _provision_gym(client)
    await _ingest(client, headers, body="Hi", external_id="wa-1")
    await _ingest(client, headers, body="Hi", external_id="wa-1")
    r = await client.get("/api/v1/inbox/conversations", headers=headers)
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["unread_count"] == 1  # deduped


@pytest.mark.asyncio
async def test_ingest_matches_member_by_email(client):
    headers, _org_id, org_code = await _provision_gym(client)
    member_id = await _signup_member(client, org_code, "findme@inbox.com")
    r = await _ingest(client, headers, channel="email", handle="findme@inbox.com", body="Hello")
    assert r.status_code == 201, r.text
    assert r.json()["member_id"] == member_id
    assert r.json()["member_name"]  # resolved name/email


@pytest.mark.asyncio
async def test_member_sms_stop_revokes_marketing_consent(client, db, monkeypatch):
    from app.services import organizations_service

    monkeypatch.setattr(organizations_service.platform_stripe, "live", False)
    headers, _org_id, org_code = await _provision_gym(client)
    member_id = await _signup_member(client, org_code, "sms-member@inbox.com")
    member = await db.get(OrganizationMember, member_id)
    member.phone = "+15555550100"
    member.marketing_sms_consent = True
    await db.commit()

    response = await _ingest(
        client, headers, channel="sms", handle=member.phone, body="STOP",
    )
    assert response.status_code == 201, response.text
    await db.refresh(member)
    assert member.marketing_sms_consent is False
    assert member.marketing_sms_consent_at is not None


# ------------------------------------------------------------------- actions
@pytest.mark.asyncio
async def test_reply_is_idempotent_and_assigns(client):
    headers, _org_id, _code = await _provision_gym(client)
    conv = (await _ingest(client, headers)).json()

    key = str(uuid.uuid4())
    r1 = await client.post(f"/api/v1/inbox/conversations/{conv['id']}/reply",
                           headers={**headers, "Idempotency-Key": key},
                           json={"body": "Yes, 6-8pm daily."})
    r2 = await client.post(f"/api/v1/inbox/conversations/{conv['id']}/reply",
                           headers={**headers, "Idempotency-Key": key},
                           json={"body": "Yes, 6-8pm daily."})
    assert r1.status_code == 200 and r2.status_code == 200, (r1.text, r2.text)
    out = r2.json()
    # 1 inbound + 1 outbound (the replay added nothing).
    assert len(out["messages"]) == 2
    assert out["messages"][-1]["direction"] == "outbound"
    assert out["assigned_to"] is not None      # auto-assigned on reply
    assert out["status"] == "pending"


@pytest.mark.asyncio
async def test_assign_and_status(client):
    headers, _org_id, _code = await _provision_gym(client)
    conv = (await _ingest(client, headers)).json()
    me = (await client.get("/api/v1/auth/me", headers=headers)).json()

    r = await client.post(f"/api/v1/inbox/conversations/{conv['id']}/assign",
                          headers=headers, json={"user_id": me["user_id"]})
    assert r.status_code == 200, r.text
    assert r.json()["assigned_to"] == me["user_id"]

    r = await client.post(f"/api/v1/inbox/conversations/{conv['id']}/status",
                          headers=headers, json={"status": "resolved"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "resolved"

    # Resolved threads drop out of the default list.
    r = await client.get("/api/v1/inbox/conversations", headers=headers)
    assert r.json() == []
    r = await client.get("/api/v1/inbox/conversations", headers=headers, params={"status": "resolved"})
    assert len(r.json()) == 1


@pytest.mark.asyncio
async def test_unassigned_filter_and_stats(client):
    headers, _org_id, _code = await _provision_gym(client)
    await _ingest(client, headers, handle="+1", body="a")
    await _ingest(client, headers, handle="+2", body="b")

    r = await client.get("/api/v1/inbox/conversations", headers=headers, params={"unassigned": True})
    assert len(r.json()) == 2

    r = await client.get("/api/v1/inbox/stats", headers=headers)
    assert r.json() == {
        "open": 2,
        "unassigned": 2,
        "mine": 0,
        "resolved": 0,
        "unread": 2,
    }


@pytest.mark.asyncio
async def test_draft_reply_returns_text(client, monkeypatch):
    from app.core.config import settings

    # Force the offline stub (assistant_live derives from the key) so the test
    # never calls a real provider.
    monkeypatch.setattr(settings, "groq_api_key", "")

    headers, _org_id, _code = await _provision_gym(client)
    conv = (await _ingest(client, headers, body="What are your opening hours?"))
    conv = conv.json()
    r = await client.post(f"/api/v1/inbox/conversations/{conv['id']}/draft", headers=headers)
    assert r.status_code == 200, r.text
    # The stub echoes the prompt, which carries the conversation.
    assert "What are your opening hours?" in r.json()["body"]


# ------------------------------------------------------------- guards
@pytest.mark.asyncio
async def test_tenant_isolation(client):
    headers_a, _org_a, _code_a = await _provision_gym(client, owner_email="a@inbox.com")
    conv = (await _ingest(client, headers_a)).json()

    headers_b, *_ = await _provision_gym(client, owner_email="b@inbox.com")
    r = await client.get(f"/api/v1/inbox/conversations/{conv['id']}", headers=headers_b)
    assert r.status_code == 404, r.text


@pytest.mark.asyncio
async def test_member_cannot_view_inbox(client):
    headers, _org_id, org_code = await _provision_gym(client)
    await _signup_member(client, org_code, "m@inbox.com")
    mh = await _member_headers(client, org_code, "m@inbox.com")
    r = await client.get("/api/v1/inbox/conversations", headers=mh)
    assert r.status_code == 403, r.text


@pytest.mark.asyncio
async def test_search_filters_conversations(client):
    headers, _org_id, _code = await _provision_gym(client)
    await _ingest(client, headers, handle="+111", body="a", contact_name="Alice")
    await _ingest(client, headers, handle="+222", body="b", contact_name="Bob")

    r = await client.get("/api/v1/inbox/conversations", headers=headers, params={"q": "alice"})
    assert r.status_code == 200, r.text
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["contact_name"] == "Alice"
