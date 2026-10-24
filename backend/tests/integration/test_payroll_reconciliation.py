from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.core.constants import PayrollStatus
from app.models.payroll import PayrollEntry, PayrollRun
from tests.helpers import provision_org


@pytest.mark.asyncio
async def test_payroll_run_closes_only_after_exact_staff_payouts_are_recorded(client, db, monkeypatch):
    from app.services import organizations_service

    monkeypatch.setattr(organizations_service.platform_stripe, "live", False)
    _, headers, org_id = await provision_org(client, email="payroll-owner@example.com", name="Pay Gym")
    profile = await client.get("/api/v1/auth/me", headers=headers)
    member_id = profile.json()["member_id"]
    run = PayrollRun(
        organization_id=org_id,
        period_start=date(2026, 10, 1),
        period_end=date(2026, 10, 31),
        status=PayrollStatus.FINALIZED,
        total_net=Decimal("375.00"),
    )
    db.add(run)
    await db.flush()
    first = PayrollEntry(
        organization_id=org_id, payroll_run_id=run.id, staff_member_id=member_id,
        net=Decimal("125.00"),
    )
    second = PayrollEntry(
        organization_id=org_id, payroll_run_id=run.id, staff_member_id=member_id,
        net=Decimal("250.00"),
    )
    db.add_all([first, second])
    await db.commit()

    old_action = await client.post(f"/api/v1/payroll/runs/{run.id}/pay", headers=headers)
    assert old_action.status_code == 409

    mismatch = await client.post(
        f"/api/v1/payroll/runs/{run.id}/entries/{first.id}/reconcile",
        headers=headers,
        json={"payout_reference": "bank-001", "paid_amount": "124.99"},
    )
    assert mismatch.status_code == 409
    assert mismatch.json()["detail"].startswith("Payout amount must match")

    payload = {"payout_reference": "bank-001", "paid_amount": "125.00"}
    response = await client.post(
        f"/api/v1/payroll/runs/{run.id}/entries/{first.id}/reconcile", headers=headers, json=payload
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "finalized"
    assert next(item for item in response.json()["entries"] if item["id"] == first.id)["payout_reference"] == "bank-001"

    # Same request is safe to retry; conflicting evidence cannot overwrite it.
    retry = await client.post(
        f"/api/v1/payroll/runs/{run.id}/entries/{first.id}/reconcile", headers=headers, json=payload
    )
    assert retry.status_code == 200, retry.text
    conflict = await client.post(
        f"/api/v1/payroll/runs/{run.id}/entries/{first.id}/reconcile",
        headers=headers,
        json={"payout_reference": "bank-other", "paid_amount": "125.00"},
    )
    assert conflict.status_code == 409

    complete = await client.post(
        f"/api/v1/payroll/runs/{run.id}/entries/{second.id}/reconcile",
        headers=headers,
        json={"payout_reference": "cash-receipt-002", "paid_amount": "250.00"},
    )
    assert complete.status_code == 200, complete.text
    assert complete.json()["status"] == "paid"
    assert all(entry["paid_at"] for entry in complete.json()["entries"])

