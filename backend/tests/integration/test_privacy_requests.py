from __future__ import annotations

import pytest

from tests.integration.test_member_detail import _member_id, _provision, _signup_and_pay


@pytest.mark.asyncio
async def test_owner_can_record_review_export_and_resolve_member_data_request(client, monkeypatch):
    from app.services import organizations_service
    monkeypatch.setattr(organizations_service.platform_stripe, "live", False)
    monkeypatch.setattr(organizations_service.connect_stripe, "live", False)
    org_code, plan_id, headers, _org_id = await _provision(client)
    email = "privacy-member@example.com"
    await _signup_and_pay(client, org_code, plan_id, email)
    member_id = await _member_id(client, headers, email)

    consent = await client.get(f"/api/v1/privacy/members/{member_id}/consent", headers=headers)
    assert consent.status_code == 200, consent.text
    assert consent.json()["email"] is False
    updated_consent = await client.put(
        f"/api/v1/privacy/members/{member_id}/consent",
        headers={**headers, "Idempotency-Key": "privacy-consent-1"},
        json={"email": True, "sms": True, "in_app": True},
    )
    assert updated_consent.status_code == 200, updated_consent.text
    assert updated_consent.json()["email_updated_at"]

    response = await client.post(
        "/api/v1/privacy/data-requests",
        headers={**headers, "Idempotency-Key": "privacy-request-1"},
        json={"member_id": member_id, "request_type": "export", "note": "Member asked for a copy."},
    )
    assert response.status_code == 201, response.text
    request = response.json()
    assert request["member_email"] == email
    assert request["status"] == "open"

    replay = await client.post(
        "/api/v1/privacy/data-requests",
        headers={**headers, "Idempotency-Key": "privacy-request-1"},
        json={"member_id": member_id, "request_type": "export", "note": "Member asked for a copy."},
    )
    assert replay.status_code == 201
    assert replay.json()["id"] == request["id"]

    export = await client.get(f"/api/v1/privacy/members/{member_id}/export", headers=headers)
    assert export.status_code == 200, export.text
    assert export.json()["account"]["email"] == email
    assert export.json()["subscriptions"]
    session = await client.post("/api/v1/classes", headers=headers, json={
        "title": "Privacy export class", "starts_at": "2026-12-01T10:00:00",
    })
    assert session.status_code == 201, session.text
    login = await client.post("/api/v1/auth/login", json={
        "org_code": org_code, "email": email, "password": "M3mberStr0ng!Pwd",
    })
    assert login.status_code == 200, login.text
    member_headers = {
        "Authorization": f"Bearer {login.json()['access_token']}",
        "X-Organization-Id": login.json()["organization_id"],
    }
    booking = await client.post("/api/v1/classes/book", headers={
        **member_headers, "Idempotency-Key": "privacy-class-booking",
    }, json={"class_session_id": session.json()["id"]})
    assert booking.status_code == 200, booking.text
    export = await client.get(f"/api/v1/privacy/members/{member_id}/export", headers=headers)
    assert export.status_code == 200, export.text
    assert len(export.json()["class_bookings"]) == 1
    assert export.json()["class_bookings"][0]["status"] == "booked"
    assert export.json()["class_bookings"][0]["class_title"] == "Privacy export class"

    resolved = await client.post(
        f"/api/v1/privacy/data-requests/{request['id']}/decision",
        headers={**headers, "Idempotency-Key": "privacy-request-decision-1"},
        json={"status": "completed", "resolution_note": "Export delivered securely."},
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["status"] == "completed"


@pytest.mark.asyncio
async def test_front_desk_cannot_export_member_private_data(client, monkeypatch):
    from app.services import organizations_service
    from tests.integration.test_attendance import _provision_front_desk

    monkeypatch.setattr(organizations_service.platform_stripe, "live", False)
    monkeypatch.setattr(organizations_service.connect_stripe, "live", False)
    org_code, plan_id, headers, _org_id = await _provision(client)
    email = "privacy-desk@example.com"
    await _signup_and_pay(client, org_code, plan_id, email)
    member_id = await _member_id(client, headers, email)
    desk_headers = await _provision_front_desk(client, headers, org_code, "privacy-desk-staff@example.com")

    response = await client.get(f"/api/v1/privacy/members/{member_id}/export", headers=desk_headers)
    assert response.status_code == 403, response.text


@pytest.mark.asyncio
async def test_data_request_rejects_missing_resolution_note(client, monkeypatch):
    from app.services import organizations_service
    monkeypatch.setattr(organizations_service.platform_stripe, "live", False)
    monkeypatch.setattr(organizations_service.connect_stripe, "live", False)
    org_code, plan_id, headers, _org_id = await _provision(client)
    email = "privacy-member-2@example.com"
    await _signup_and_pay(client, org_code, plan_id, email)
    member_id = await _member_id(client, headers, email)
    created = await client.post(
        "/api/v1/privacy/data-requests",
        headers={**headers, "Idempotency-Key": "privacy-request-2"},
        json={"member_id": member_id, "request_type": "erasure"},
    )
    assert created.status_code == 201, created.text
    rejected = await client.post(
        f"/api/v1/privacy/data-requests/{created.json()['id']}/decision",
        headers={**headers, "Idempotency-Key": "privacy-request-decision-2"},
        json={"status": "completed"},
    )
    assert rejected.status_code == 422


@pytest.mark.asyncio
async def test_erasure_redacts_profile_but_keeps_financial_evidence(client, monkeypatch):
    from app.services import organizations_service

    monkeypatch.setattr(organizations_service.platform_stripe, "live", False)
    monkeypatch.setattr(organizations_service.connect_stripe, "live", False)
    org_code, plan_id, headers, _org_id = await _provision(client)
    email = "privacy-erasure@example.com"
    await _signup_and_pay(client, org_code, plan_id, email)
    member_id = await _member_id(client, headers, email)
    created = await client.post(
        "/api/v1/privacy/data-requests",
        headers={**headers, "Idempotency-Key": "privacy-erasure-1"},
        json={"member_id": member_id, "request_type": "erasure"},
    )
    assert created.status_code == 201, created.text

    premature = await client.post(
        f"/api/v1/privacy/data-requests/{created.json()['id']}/decision",
        headers={**headers, "Idempotency-Key": "privacy-erasure-done-1"},
        json={"status": "completed", "resolution_note": "Verified request."},
    )
    assert premature.status_code == 409

    for item in ("identity", "linked_records", "processors", "retention_backups"):
        evidence = await client.put(
            f"/api/v1/privacy/data-requests/{created.json()['id']}/review",
            headers={**headers, "Idempotency-Key": f"privacy-review-{item}"},
            json={"item": item, "outcome": "verified", "note": f"Reviewed {item}; reference TEST-123."},
        )
        assert evidence.status_code == 200, evidence.text

    review = await client.post(
        f"/api/v1/privacy/data-requests/{created.json()['id']}/decision",
        headers={**headers, "Idempotency-Key": "privacy-erasure-review-1"},
        json={"status": "in_review"},
    )
    assert review.status_code == 200, review.text
    assert review.json()["erasure_redacted_at"]

    result = await client.post(
        f"/api/v1/privacy/data-requests/{created.json()['id']}/decision",
        headers={**headers, "Idempotency-Key": "privacy-erasure-done-2"},
        json={"status": "completed", "resolution_note": "Linked records and retention reviewed."},
    )
    assert result.status_code == 200, result.text
    assert result.json()["member_name"] == "Erased member"
    export = await client.get(f"/api/v1/privacy/members/{member_id}/export", headers=headers)
    assert export.status_code == 200, export.text
    body = export.json()
    assert body["account"]["email"].endswith("@privacy.invalid")
    assert body["membership"]["health_notes"] is None
    assert body["payments"]
    assert body["subscriptions"][0]["status"] == "cancelled"
