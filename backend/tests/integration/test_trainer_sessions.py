from __future__ import annotations

import uuid
from datetime import timedelta

import pytest

from app.core.security import now_utc
from tests.helpers import PASSWORD, latest_code_for, provision_org


async def _signup(client, org_code: str, plan_id: str, email: str) -> dict:
    await client.post("/api/v1/memberships/signup/request-email", json={"org_code": org_code, "email": email})
    code = latest_code_for(email)
    await client.post("/api/v1/memberships/signup/verify-email", json={"org_code": org_code, "email": email, "code": code})
    created = await client.post("/api/v1/memberships/signup/set-password", json={
        "org_code": org_code, "email": email, "password": "M3mberStr0ng!Pwd",
    })
    paid = await client.post("/api/v1/memberships/signup/pay", headers={
        "Idempotency-Key": str(uuid.uuid4()),
    }, json={"org_code": org_code, "email": email, "plan_id": plan_id})
    assert paid.status_code == 200, paid.text
    return {"member_id": created.json()["member_id"], "email": email}


@pytest.mark.asyncio
async def test_trainer_can_log_only_for_assigned_active_clients(client, monkeypatch):
    from app.services import organizations_service
    from app.integrations.stripe_connect import connect_stripe

    monkeypatch.setattr(organizations_service.platform_stripe, "live", False)
    monkeypatch.setattr(connect_stripe, "live", False)
    org_code, owner, org_id = await provision_org(
        client, email="trainer-log-owner@example.com", name="Trainer Log Gym"
    )
    await client.post("/api/v1/organizations/me/connect", headers=owner)
    await client.post("/api/v1/organizations/me/connect/complete", headers=owner)
    plan = await client.post("/api/v1/plans", headers=owner, json={
        "name": "Monthly", "price": 99, "billing_type": "recurring",
        "cycle_unit": "month", "cycle_length": 1,
    })
    plan_id = plan.json()["id"]
    await client.post(f"/api/v1/plans/{plan_id}/publish", headers=owner)
    assigned = await _signup(client, org_code, plan_id, "training-client@example.com")
    unassigned = await _signup(client, org_code, plan_id, "unassigned-client@example.com")

    invite = await client.post("/api/v1/staff/invites", headers=owner, json={
        "role": "trainer", "email": "trainer-log@example.com",
    })
    redeemed = await client.post("/api/v1/staff/invites/redeem", json={
        "code": invite.json()["code"], "full_name": "Coach Lee", "password": PASSWORD,
    })
    trainer = {"Authorization": f"Bearer {redeemed.json()['access_token']}", "X-Organization-Id": org_id}
    trainer_member_id = (await client.get("/api/v1/auth/me", headers=trainer)).json()["member_id"]
    linked = await client.post(f"/api/v1/members/{assigned['member_id']}/trainers", headers=owner,
                               json={"trainer_member_id": trainer_member_id})
    assert linked.status_code == 201, linked.text

    payload = {
        "client_member_id": assigned["member_id"],
        "performed_at": (now_utc() - timedelta(minutes=30)).isoformat(),
        "duration_minutes": 50,
        "focus": "Strength",
        "notes": "Squats and mobility work.",
    }
    saved = await client.post("/api/v1/staff/trainer-sessions", headers=trainer, json=payload)
    assert saved.status_code == 201, saved.text
    assert saved.json()["client_name"] == assigned["email"]
    assert saved.json()["notes"] == payload["notes"]

    denied = await client.post("/api/v1/staff/trainer-sessions", headers=trainer, json={
        **payload, "client_member_id": unassigned["member_id"],
    })
    assert denied.status_code == 403
    history = await client.get("/api/v1/staff/trainer-sessions", headers=trainer)
    assert [row["id"] for row in history.json()] == [saved.json()["id"]]
