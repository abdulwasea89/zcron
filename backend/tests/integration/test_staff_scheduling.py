from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from tests.helpers import OWNER_PROFILE, latest_code_for

PASSWORD = "Sup3rStr0ng!Pass"


async def _owner(client):
    email = "schedule-owner@example.com"
    await client.post("/api/v1/auth/register", json={
        "full_name": "Schedule Owner", "email": email,
        "password": PASSWORD, "confirm_password": PASSWORD, **OWNER_PROFILE,
    })
    code = latest_code_for(email)
    await client.post("/api/v1/auth/verify-email", json={"email": email, "code": code})
    response = await client.post("/api/v1/organizations/register", json={
        "owner_email": email,
        "details": {"name": "Schedule Gym", "default_currency": "USD"},
        "tier": "pro",
    })
    body = response.json()
    headers = {"Authorization": f"Bearer {body['access_token']}",
               "X-Organization-Id": body["organization"]["id"]}
    return headers


@pytest.mark.asyncio
async def test_owner_can_schedule_staff_and_overlaps_are_rejected(client, monkeypatch):
    from app.services import organizations_service

    monkeypatch.setattr(organizations_service.platform_stripe, "live", False)
    owner = await _owner(client)
    invite = await client.post("/api/v1/staff/invites", headers=owner,
                               json={"role": "trainer", "email": "coach@example.com"})
    redeemed = await client.post("/api/v1/staff/invites/redeem", json={
        "code": invite.json()["code"], "full_name": "Coach", "password": PASSWORD,
    })
    trainer_headers = {
        "Authorization": f"Bearer {redeemed.json()['access_token']}",
        "X-Organization-Id": owner["X-Organization-Id"],
    }
    profile = await client.get("/api/v1/auth/me", headers=trainer_headers)
    member_id = profile.json()["member_id"]
    starts = datetime.now(timezone.utc) + timedelta(days=1)
    payload = {"staff_member_id": member_id, "starts_at": starts.isoformat(),
               "ends_at": (starts + timedelta(hours=2)).isoformat(), "note": "Opening shift"}

    created = await client.post("/api/v1/staff/schedule", headers=owner, json=payload)
    assert created.status_code == 201, created.text
    assert created.json()["staff_member_id"] == member_id
    assert (await client.get("/api/v1/staff/schedule", headers=owner)).json()[0]["note"] == "Opening shift"
    assert len((await client.get("/api/v1/staff/schedule/mine", headers=trainer_headers)).json()) == 1
    assert (await client.post("/api/v1/staff/schedule", headers=owner, json=payload)).status_code == 409
    assert (await client.get("/api/v1/staff/schedule", headers=trainer_headers)).status_code == 403


@pytest.mark.asyncio
async def test_owner_manages_recurring_trainer_availability(client, monkeypatch):
    from app.services import organizations_service

    monkeypatch.setattr(organizations_service.platform_stripe, "live", False)
    owner = await _owner(client)
    invite = await client.post("/api/v1/staff/invites", headers=owner,
                               json={"role": "trainer", "email": "availability-coach@example.com"})
    redeemed = await client.post("/api/v1/staff/invites/redeem", json={
        "code": invite.json()["code"], "full_name": "Availability Coach", "password": PASSWORD,
    })
    trainer_headers = {
        "Authorization": f"Bearer {redeemed.json()['access_token']}",
        "X-Organization-Id": owner["X-Organization-Id"],
    }
    trainer_id = (await client.get("/api/v1/auth/me", headers=trainer_headers)).json()["member_id"]
    payload = {
        "trainer_member_id": trainer_id, "weekday": 0,
        "start_time": "09:00", "end_time": "12:00",
    }

    created = await client.post("/api/v1/staff/availability", headers=owner, json=payload)
    assert created.status_code == 201, created.text
    overlap = await client.post("/api/v1/staff/availability", headers=owner, json={
        **payload, "start_time": "11:00", "end_time": "13:00",
    })
    assert overlap.status_code == 409
    assert len((await client.get("/api/v1/staff/availability", headers=owner)).json()) == 1
    assert len((await client.get("/api/v1/staff/availability", headers=trainer_headers)).json()) == 1
    assert (await client.post("/api/v1/staff/availability", headers=trainer_headers, json=payload)).status_code == 403

    removed = await client.delete(
        f"/api/v1/staff/availability/{created.json()['id']}", headers=owner,
    )
    assert removed.status_code == 200
    assert (await client.get("/api/v1/staff/availability", headers=owner)).json() == []
