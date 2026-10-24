from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app.core.constants import PayrollStatus
from app.models.membership import OrganizationMember
from app.models.payroll import PayrollEntry, PayrollRun
from tests.helpers import PASSWORD, provision_org


@pytest.mark.asyncio
async def test_staff_sees_only_own_finalized_pay_statements(client, db, monkeypatch):
    from app.services import organizations_service

    monkeypatch.setattr(organizations_service.platform_stripe, "live", False)
    _org_code, owner_headers, org_id = await provision_org(
        client, email="pay-owner@example.com", name="Pay Gym"
    )
    invite = await client.post("/api/v1/staff/invites", headers=owner_headers, json={
        "role": "trainer", "email": "pay-trainer@example.com",
    })
    redeemed = await client.post("/api/v1/staff/invites/redeem", json={
        "code": invite.json()["code"], "full_name": "Pay Trainer", "password": PASSWORD,
    })
    staff_headers = {
        "Authorization": f"Bearer {redeemed.json()['access_token']}",
        "X-Organization-Id": org_id,
    }
    profile = await client.get("/api/v1/auth/me", headers=staff_headers)
    owner_profile = await client.get("/api/v1/auth/me", headers=owner_headers)
    trainer = await db.get(OrganizationMember, profile.json()["member_id"])
    owner = await db.get(OrganizationMember, owner_profile.json()["member_id"])
    paid_run = PayrollRun(organization_id=org_id, period_start=date(2026, 9, 1),
                         period_end=date(2026, 9, 30), status=PayrollStatus.PAID)
    owner_run = PayrollRun(organization_id=org_id, period_start=date(2026, 8, 1),
                          period_end=date(2026, 8, 31), status=PayrollStatus.PAID)
    draft_run = PayrollRun(organization_id=org_id, period_start=date(2026, 10, 1),
                           period_end=date(2026, 10, 31), status=PayrollStatus.DRAFT)
    db.add_all([paid_run, owner_run, draft_run])
    await db.flush()
    db.add_all([
        PayrollEntry(organization_id=org_id, payroll_run_id=paid_run.id,
                     staff_member_id=trainer.id, net=Decimal("123.45"),
                     paid_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
                     paid_amount=Decimal("123.45"), payout_reference="transfer-123"),
        PayrollEntry(organization_id=org_id, payroll_run_id=owner_run.id,
                     staff_member_id=owner.id, net=Decimal("999.99")),
        PayrollEntry(organization_id=org_id, payroll_run_id=draft_run.id,
                     staff_member_id=trainer.id, net=Decimal("777.77")),
    ])
    await db.commit()

    response = await client.get("/api/v1/payroll/me", headers=staff_headers)
    assert response.status_code == 200, response.text
    assert len(response.json()) == 1
    assert response.json()[0]["net"] == 123.45
    assert response.json()[0]["run_status"] == "paid"
    assert response.json()[0]["payout_method"] == "bank_transfer"
    assert response.json()[0]["paid_amount"] == 123.45
    assert response.json()[0]["payout_reference"] == "transfer-123"
