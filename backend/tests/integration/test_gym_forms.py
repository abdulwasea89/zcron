"""Admin-managed waivers and staff-collected signed health evidence."""

from __future__ import annotations

import pytest

from tests.integration.test_onboarding import _member_headers, _provision_gym, _signup_member

PASSWORD = "Sup3rStr0ng!Pass"


@pytest.mark.asyncio
async def test_form_versions_acceptance_evidence_and_member_access(client):
    headers, _org_id, org_code, plan_id = await _provision_gym(
        client, owner_email="owner@gymforms.com",
    )
    member_id = await _signup_member(client, org_code, plan_id, "signer@gymforms.com")

    created = await client.post("/api/v1/gym-forms/forms", headers=headers, json={
        "title": "Gym waiver", "form_type": "waiver",
        "body": "I understand the gym rules and assume the risks of exercise.",
    })
    assert created.status_code == 201, created.text
    old_form = created.json()

    updated = await client.post(
        f"/api/v1/gym-forms/forms/{old_form['id']}/versions", headers=headers, json={
            "title": "Gym waiver", "form_type": "waiver",
            "body": "I understand the updated gym rules and assume exercise risks.",
        },
    )
    assert updated.status_code == 201, updated.text
    assert updated.json()["version"] == 2
    forms = (await client.get("/api/v1/gym-forms/forms", headers=headers)).json()
    assert next(row for row in forms if row["id"] == old_form["id"])["active"] is False

    member_headers = await _member_headers(client, org_code, "signer@gymforms.com")
    assert (await client.get("/api/v1/gym-forms/forms", headers=member_headers)).status_code == 403
    assert (await client.get("/api/v1/gym-forms/collection-forms", headers=member_headers)).status_code == 403

    signed_pdf = b"%PDF-1.7\nGym form signed evidence"
    acceptance = await client.post(
        f"/api/v1/gym-forms/members/{member_id}/acceptances",
        headers=headers,
        data={"form_id": updated.json()["id"], "signed_by_name": "Signer Person"},
        files={"file": ("waiver.pdf", signed_pdf, "application/pdf")},
    )
    assert acceptance.status_code == 201, acceptance.text
    record = acceptance.json()
    assert record["form_version"] == 2
    assert record["evidence_sha256"]
    assert "form_body_snapshot" not in record

    rows = await client.get(
        f"/api/v1/gym-forms/members/{member_id}/acceptances", headers=headers,
    )
    assert rows.status_code == 200
    assert rows.json()[0]["form_version"] == 2
    evidence = await client.get(
        f"/api/v1/gym-forms/acceptances/{record['id']}/evidence", headers=headers,
    )
    assert evidence.content == signed_pdf
    assert evidence.headers["content-disposition"].startswith("attachment;")
    assert evidence.headers["cache-control"] == "private, no-store"

    duplicate = await client.post(
        f"/api/v1/gym-forms/members/{member_id}/acceptances",
        headers=headers,
        data={"form_id": updated.json()["id"], "signed_by_name": "Signer Person"},
        files={"file": ("waiver.pdf", signed_pdf, "application/pdf")},
    )
    assert duplicate.status_code == 409


@pytest.mark.asyncio
async def test_signed_evidence_rejects_invalid_files_and_is_tenant_scoped(client):
    owner_headers, _org_id, org_code, plan_id = await _provision_gym(
        client, owner_email="owner@forms-security.com",
    )
    member_id = await _signup_member(client, org_code, plan_id, "one@forms-security.com")
    other_headers, _other_org, _other_code, _other_plan = await _provision_gym(
        client, owner_email="other@forms-security.com",
    )
    form = await client.post("/api/v1/gym-forms/forms", headers=owner_headers, json={
        "title": "Health questionnaire", "form_type": "health",
        "body": "Please review and sign the gym health questionnaire.",
    })
    rejected = await client.post(
        f"/api/v1/gym-forms/members/{member_id}/acceptances",
        headers=owner_headers,
        data={"form_id": form.json()["id"], "signed_by_name": "Signer Person"},
        files={"file": ("fake.pdf", b"not a PDF", "application/pdf")},
    )
    assert rejected.status_code == 422
    assert (await client.get(
        "/api/v1/gym-forms/forms", headers=other_headers,
    )).json() == []
    assert (await client.get(
        f"/api/v1/gym-forms/members/{member_id}/acceptances", headers=other_headers,
    )).status_code == 404
