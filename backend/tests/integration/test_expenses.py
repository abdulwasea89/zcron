from __future__ import annotations

import pytest

from tests.integration.test_domains import _provision_gym


@pytest.mark.asyncio
async def test_expense_ledger_is_idempotent_tenant_scoped_and_voidable(client):
    owner_headers, *_ = await _provision_gym(client, owner_email="expense-owner@g.com")
    other_headers, *_ = await _provision_gym(client, owner_email="other-expense-owner@g.com")
    payload = {
        "category": "utilities", "description": "October electricity", "vendor": "Power Co",
        "amount": "120.35", "currency": "USD", "incurred_on": "2026-10-25",
    }
    headers = {**owner_headers, "Idempotency-Key": "expense-create-1"}

    created = await client.post("/api/v1/expenses", headers=headers, json=payload)
    replay = await client.post("/api/v1/expenses", headers=headers, json=payload)
    assert created.status_code == 201, created.text
    assert replay.status_code == 201, replay.text
    assert replay.json()["id"] == created.json()["id"]

    owner_list = await client.get("/api/v1/expenses", headers=owner_headers)
    other_list = await client.get("/api/v1/expenses", headers=other_headers)
    assert owner_list.json()["totals_by_currency"] == {"USD": "120.35"}
    assert len(owner_list.json()["items"]) == 1
    assert other_list.json()["items"] == []

    outside_range = await client.get(
        "/api/v1/expenses", headers=owner_headers,
        params={"date_from": "2026-11-01", "date_to": "2026-11-30"},
    )
    assert outside_range.json()["items"] == []
    assert outside_range.json()["totals_by_currency"] == {}

    voided = await client.post(
        f"/api/v1/expenses/{created.json()['id']}/void",
        headers={**owner_headers, "Idempotency-Key": "expense-void-1"},
        json={"reason": "Duplicate entry"},
    )
    assert voided.status_code == 200, voided.text
    after_void = await client.get("/api/v1/expenses", headers=owner_headers)
    assert after_void.json()["totals_by_currency"] == {}
    assert after_void.json()["items"][0]["voided_at"]
