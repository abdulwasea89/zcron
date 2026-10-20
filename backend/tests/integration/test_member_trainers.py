"""Integration tests for trainer-to-member assignment.

Covers: assign (owner), duplicate rejection, soft unassign, role validation,
tenant isolation, and the trainer's "assigned-to-me" client view.
"""

from __future__ import annotations

import uuid

import pytest

from tests.helpers import OWNER_PROFILE, latest_code_for

PASSWORD = "Sup3rStr0ng!Pass"
MEMBER_PWD = "M3mberStr0ng!Pwd"


async def _provision_gym(client, *, owner_email="owner@g.com"):
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
    org_code = body["organization"]["org_code"]
    headers = {"Authorization": f"Bearer {body['access_token']}", "X-Organization-Id": org_id}
    await client.post("/api/v1/organizations/me/connect", headers=headers)
    await client.post("/api/v1/organizations/me/connect/complete", headers=headers)
    r = await client.post("/api/v1/plans", headers=headers, json={
        "name": "Monthly", "price": 149.0, "billing_type": "recurring",
        "cycle_unit": "month", "cycle_length": 1})
    plan_id = r.json()["id"]
    await client.post(f"/api/v1/plans/{plan_id}/publish", headers=headers)
    return headers, org_id, org_code, plan_id


async def _signup_member(client, org_code, plan_id, email) -> dict:
    await client.post("/api/v1/memberships/signup/request-email",
                      json={"org_code": org_code, "email": email})
    code = latest_code_for(email)
    await client.post("/api/v1/memberships/signup/verify-email",
                      json={"org_code": org_code, "email": email, "code": code})
    r = await client.post("/api/v1/memberships/signup/set-password",
                          json={"org_code": org_code, "email": email, "password": MEMBER_PWD})
    member_id = r.json()["member_id"]
    r = await client.post("/api/v1/memberships/signup/pay",
                          headers={"Idempotency-Key": str(uuid.uuid4())},
                          json={"org_code": org_code, "email": email, "plan_id": plan_id})
    body = r.json()
    return {"member_id": member_id, "org_id": body["organization_id"]}


async def _provision_trainer(client, headers, email, name="Marcus Trainer") -> str:
    """Invite + redeem a trainer; returns their member_id."""

    r = await client.post("/api/v1/staff/invites", headers=headers,
                          json={"role": "trainer", "email": email})
    invite_code = r.json()["code"]
    r = await client.post("/api/v1/staff/invites/redeem", json={
        "code": invite_code, "full_name": name, "password": PASSWORD})
    body = r.json()
    trainer_headers = {"Authorization": f"Bearer {body['access_token']}",
                       "X-Organization-Id": body["organization_id"]}
    r = await client.get("/api/v1/members", headers=headers, params={"role": "trainer"})
    trainer = [m for m in r.json() if m["email"] == email][0]
    return trainer["member_id"], trainer_headers


# ------------------------------------------------------------------- assign
@pytest.mark.asyncio
async def test_assign_trainer_shows_in_directory(client):
    headers, org_id, org_code, plan_id = await _provision_gym(client)
    member = await _signup_member(client, org_code, plan_id, "member@t.com")
    trainer_id, _ = await _provision_trainer(client, headers, "trainer@t.com", "Marcus Trainer")

    r = await client.post(f"/api/v1/members/{member['member_id']}/trainers",
                          headers=headers, json={"trainer_member_id": trainer_id})
    assert r.status_code == 201, r.text
    assert r.json()["trainer_member_id"] == trainer_id
    assert r.json()["trainer_name"] == "Marcus Trainer"

    # The member directory carries the assigned trainer's name.
    r = await client.get("/api/v1/members", headers=headers)
    row = [m for m in r.json() if m["member_id"] == member["member_id"]][0]
    assert row["assigned_trainers"] == ["Marcus Trainer"]

    # GET /members/{id}/trainers returns it.
    r = await client.get(f"/api/v1/members/{member['member_id']}/trainers", headers=headers)
    assert r.status_code == 200, r.text
    assert [t["trainer_member_id"] for t in r.json()] == [trainer_id]


@pytest.mark.asyncio
async def test_trainer_task_list_only_includes_tasks_assigned_to_them(client):
    headers, _org_id, _org_code, _plan_id = await _provision_gym(client)
    trainer_id, trainer_headers = await _provision_trainer(client, headers, "task-trainer@t.com")

    own = await client.post("/api/v1/staff/tasks", headers=headers, json={
        "title": "Prepare member program", "assignee_member_id": trainer_id,
    })
    other = await client.post("/api/v1/staff/tasks", headers=headers, json={
        "title": "Review attendance",
    })
    assert own.status_code == other.status_code == 201

    trainer_tasks = await client.get("/api/v1/staff/tasks", headers=trainer_headers)
    assert trainer_tasks.status_code == 200, trainer_tasks.text
    assert {task["id"] for task in trainer_tasks.json()} == {own.json()["id"]}

    assert (await client.post(f"/api/v1/staff/tasks/{other.json()['id']}/complete", headers=trainer_headers)).status_code == 404
    assert (await client.patch(f"/api/v1/staff/tasks/{other.json()['id']}", headers=trainer_headers, json={"title": "Changed"})).status_code == 404
    assert (await client.delete(f"/api/v1/staff/tasks/{other.json()['id']}", headers=trainer_headers)).status_code == 404
    assert (await client.patch(f"/api/v1/staff/tasks/{own.json()['id']}", headers=trainer_headers, json={"assignee_member_id": "someone-else"})).status_code == 403
    assert (await client.post(f"/api/v1/staff/tasks/{own.json()['id']}/complete", headers=trainer_headers)).status_code == 200

    owner_tasks = await client.get("/api/v1/staff/tasks", headers=headers)
    assert {task["id"] for task in owner_tasks.json()} == {own.json()["id"], other.json()["id"]}


@pytest.mark.asyncio
async def test_duplicate_assign_rejected(client):
    headers, _org_id, org_code, plan_id = await _provision_gym(client)
    member = await _signup_member(client, org_code, plan_id, "member@dup.com")
    trainer_id, _ = await _provision_trainer(client, headers, "trainer@dup.com")

    url = f"/api/v1/members/{member['member_id']}/trainers"
    assert (await client.post(url, headers=headers, json={"trainer_member_id": trainer_id})).status_code == 201
    r = await client.post(url, headers=headers, json={"trainer_member_id": trainer_id})
    assert r.status_code == 409, r.text


@pytest.mark.asyncio
async def test_unassign_is_soft_and_removes_from_directory(client):
    headers, _org_id, org_code, plan_id = await _provision_gym(client)
    member = await _signup_member(client, org_code, plan_id, "member@un.com")
    trainer_id, _ = await _provision_trainer(client, headers, "trainer@un.com")

    await client.post(f"/api/v1/members/{member['member_id']}/trainers",
                      headers=headers, json={"trainer_member_id": trainer_id})
    r = await client.delete(f"/api/v1/members/{member['member_id']}/trainers/{trainer_id}",
                            headers=headers)
    assert r.status_code == 200, r.text

    r = await client.get(f"/api/v1/members/{member['member_id']}/trainers", headers=headers)
    assert r.json() == []

    r = await client.get("/api/v1/members", headers=headers)
    row = [m for m in r.json() if m["member_id"] == member["member_id"]][0]
    assert row["assigned_trainers"] == []

    # Unassigning again 404s.
    r = await client.delete(f"/api/v1/members/{member['member_id']}/trainers/{trainer_id}",
                            headers=headers)
    assert r.status_code == 404, r.text


# ---------------------------------------------------------------- validation
@pytest.mark.asyncio
async def test_assign_rejects_non_trainer_member(client):
    headers, _org_id, org_code, plan_id = await _provision_gym(client)
    member = await _signup_member(client, org_code, plan_id, "member@nt.com")
    other = await _signup_member(client, org_code, plan_id, "member2@nt.com")

    r = await client.post(f"/api/v1/members/{member['member_id']}/trainers",
                          headers=headers, json={"trainer_member_id": other["member_id"]})
    assert r.status_code == 422, r.text


@pytest.mark.asyncio
async def test_assign_rejects_trainer_as_the_member(client):
    headers, _org_id, org_code, plan_id = await _provision_gym(client)
    await _signup_member(client, org_code, plan_id, "member@tm.com")
    trainer_id, _ = await _provision_trainer(client, headers, "trainer@tm.com")

    r = await client.post(f"/api/v1/members/{trainer_id}/trainers",
                          headers=headers, json={"trainer_member_id": trainer_id})
    assert r.status_code == 422, r.text


@pytest.mark.asyncio
async def test_assign_is_tenant_isolated(client):
    headers, _org_id, org_code, plan_id = await _provision_gym(client)
    member = await _signup_member(client, org_code, plan_id, "member@iso.com")
    trainer_id, _ = await _provision_trainer(client, headers, "trainer@iso.com")

    other_headers, *_ = await _provision_gym(client, owner_email="owner2@iso.com")
    # A trainer from another org does not exist here -> 404.
    r = await client.post(f"/api/v1/members/{member['member_id']}/trainers",
                          headers=headers, json={"trainer_member_id": trainer_id})
    assert r.status_code == 201, r.text
    # The second org cannot see the first org's member -> 404.
    r = await client.post(f"/api/v1/members/{member['member_id']}/trainers",
                          headers=other_headers, json={"trainer_member_id": trainer_id})
    assert r.status_code == 404, r.text


@pytest.mark.asyncio
async def test_member_cannot_assign_trainers(client):
    headers, _org_id, org_code, plan_id = await _provision_gym(client)
    member = await _signup_member(client, org_code, plan_id, "member@noperm.com")
    trainer_id, _ = await _provision_trainer(client, headers, "trainer@noperm.com")

    r = await client.post(f"/api/v1/members/{member['member_id']}/trainers",
                          headers=headers, json={"trainer_member_id": trainer_id})
    assert r.status_code == 201, r.text

    # The member's own token cannot read the assignment list.
    r = await client.post("/api/v1/auth/member-login",
                          json={"org_code": org_code, "email": "member@noperm.com", "password": MEMBER_PWD})
    mh = {"Authorization": f"Bearer {r.json()['access_token']}", "X-Organization-Id": r.json()["organization_id"]}
    r = await client.get(f"/api/v1/members/{member['member_id']}/trainers", headers=mh)
    assert r.status_code == 403, r.text


# -------------------------------------------------------------- my clients
@pytest.mark.asyncio
async def test_trainer_sees_only_their_clients(client):
    headers, _org_id, org_code, plan_id = await _provision_gym(client)
    m1 = await _signup_member(client, org_code, plan_id, "c1@t.com")
    m2 = await _signup_member(client, org_code, plan_id, "c2@t.com")
    t1, t1h = await _provision_trainer(client, headers, "trainer@clients.com", "Client Coach")
    t2, _ = await _provision_trainer(client, headers, "trainer2@clients.com", "Other Coach")

    # t1 coaches m1; t2 coaches m2.
    await client.post(f"/api/v1/members/{m1['member_id']}/trainers",
                      headers=headers, json={"trainer_member_id": t1})
    await client.post(f"/api/v1/members/{m2['member_id']}/trainers",
                      headers=headers, json={"trainer_member_id": t2})

    r = await client.get("/api/v1/members/assigned-to-me", headers=t1h)
    assert r.status_code == 200, r.text
    clients = r.json()
    assert [c["member_id"] for c in clients] == [m1["member_id"]]
    assert clients[0]["member_email"] == "c1@t.com"

    # Admin sees the whole roster.
    r = await client.get("/api/v1/members/assigned-to-me", headers=headers)
    assert len(r.json()) == 2
