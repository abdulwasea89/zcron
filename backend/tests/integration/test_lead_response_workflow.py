from __future__ import annotations

import pytest
from sqlmodel import select

from app.models.lead import Lead
from app.models.staff import Task
from tests.helpers import provision_org


@pytest.mark.asyncio
async def test_consented_lead_gets_immediate_first_email(client, monkeypatch):
    from app.services import leads_service, organizations_service

    monkeypatch.setattr(organizations_service.platform_stripe, "live", False)
    sent = []

    async def send(to, subject, body):
        sent.append((to, subject, body))
        return True

    monkeypatch.setattr(leads_service, "send_email_safe", send)
    _, headers, _ = await provision_org(client, email="lead-owner@example.com", name="Lead Gym")
    response = await client.post("/api/v1/leads", headers={**headers, "Idempotency-Key": "lead-create-1"}, json={
        "name": "Sam Lead", "email": "sam@example.com", "email_followup_consent": True,
    })
    assert response.status_code == 201, response.text
    assert len(sent) == 1 and sent[0][0] == "sam@example.com"
    followups = await client.get(f"/api/v1/leads/{response.json()['id']}/followups", headers=headers)
    day_zero = next(row for row in followups.json() if row["day"] == 0)
    assert day_zero["email_status"] == "sent"
    assert day_zero["email_sent_at"] is not None


@pytest.mark.asyncio
async def test_missed_call_assigns_callback_and_texts_only_with_consent(client, db, monkeypatch):
    from app.services import inbox_service, organizations_service

    monkeypatch.setattr(organizations_service.platform_stripe, "live", False)
    _, headers, org_id = await provision_org(client, email="call-owner@example.com", name="Call Gym")
    lead_response = await client.post("/api/v1/leads", headers={**headers, "Idempotency-Key": "lead-create-2"}, json={
        "name": "Pat Prospect", "phone": "+14155550100", "sms_followup_consent": True,
    })
    assert lead_response.status_code == 201, lead_response.text
    lead_id = lead_response.json()["id"]
    calls = []

    async def send_reply(session, **kwargs):
        calls.append(kwargs)
        return {"messages": [{"direction": "outbound", "delivery_status": "sent"}]}

    monkeypatch.setattr(inbox_service, "reply", send_reply)
    headers_with_key = {**headers, "Idempotency-Key": "missed-call-1"}
    response = await client.post(f"/api/v1/leads/{lead_id}/missed-call", headers=headers_with_key, json={})
    assert response.status_code == 200, response.text
    assert response.json()["sms_status"] == "sent"
    assert len(calls) == 1
    replay = await client.post(f"/api/v1/leads/{lead_id}/missed-call", headers=headers_with_key, json={})
    assert replay.status_code == 200 and len(calls) == 1

    task = await db.get(Task, response.json()["task_id"])
    assert task and task.assignee_member_id == (await client.get("/api/v1/auth/me", headers=headers)).json()["member_id"]

    lead = await db.get(Lead, lead_id)
    assert lead.phone == "+14155550100"
    assert (await db.execute(select(Lead.id).where(
        Lead.organization_id == org_id, Lead.phone == lead.phone, Lead.sms_followup_consent.is_(True),
    ))).scalar_one() == lead_id
    await inbox_service.record_inbound(
        db, org_id=org_id, channel="sms", handle=lead.phone,
        body="STOP", external_id="stop-message-1",
    )
    await db.commit()
    await db.refresh(lead)
    assert lead.sms_followup_consent is False
    await db.commit()
    no_consent = await client.post(
        f"/api/v1/leads/{lead_id}/missed-call",
        headers={**headers, "Idempotency-Key": "missed-call-2"}, json={},
    )
    assert no_consent.status_code == 200
    assert no_consent.json()["sms_status"] == "skipped_no_consent"
    assert len(calls) == 1
