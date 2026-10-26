from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.core.constants import PaymentStatus
from app.models.gym_invoice import GymInvoice
from app.models.payment import Payment
from app.services import gym_invoices_service as invoices


def test_overdue_status_is_derived_without_mutating_invoice():
    invoice = GymInvoice(
        organization_id="org", member_id="member", invoice_number="GINV-1", description="Training",
        issue_date=date(2026, 1, 1), due_date=date(2026, 1, 2), status="sent",
        subtotal=Decimal("10"), tax_amount=Decimal("0"), total=Decimal("10"), currency="USD",
    )
    assert invoices.displayed_status(invoice, Decimal("0"), date(2026, 1, 3)) == "overdue"
    assert invoice.status == "sent"


@pytest.mark.asyncio
async def test_invoice_payment_links_tenant_and_invoice_and_is_partially_collectible(monkeypatch):
    invoice = GymInvoice(
        id="inv", organization_id="org", member_id="member", invoice_number="GINV-1",
        description="Training", issue_date=date.today(), due_date=date.today(), status="sent",
        subtotal=Decimal("100.00"), tax_amount=Decimal("0"), total=Decimal("100.00"), currency="USD",
    )
    added = []

    class Session:
        async def get(self, model, *_args, **_kwargs):
            if model is GymInvoice:
                return invoice
            return SimpleNamespace(organization_id="org")

        def add(self, item):
            added.append(item)

        async def flush(self):
            pass

    async def claim(*_args, **_kwargs):
        return SimpleNamespace(claimed=True, record=object())

    async def paid(*_args, **_kwargs):
        return Decimal("0.00")

    async def complete(*_args, **_kwargs):
        pass

    async def audit(*_args, **_kwargs):
        pass

    monkeypatch.setattr(invoices.idempotency_service, "claim", claim)
    monkeypatch.setattr(invoices.idempotency_service, "complete", complete)
    monkeypatch.setattr(invoices, "_paid", paid)
    monkeypatch.setattr(invoices, "record_audit", audit)
    result = await invoices.record_payment(
        Session(), org_id="org", invoice_id="inv", amount=Decimal("35.50"), method="cash",
        note=None, paid_on=None, actor_id="owner", idempotency_key="unique-key",
    )
    payment = next(row for row in added if isinstance(row, Payment))
    assert result.status == "partial"
    assert payment.organization_id == "org" and payment.member_id == "member"
    assert payment.gym_invoice_id == "inv" and payment.status == PaymentStatus.SUCCEEDED
    assert payment.amount == 35.5


@pytest.mark.asyncio
async def test_invoice_payment_rejects_amount_above_balance(monkeypatch):
    invoice = GymInvoice(
        id="inv", organization_id="org", member_id="member", invoice_number="GINV-1",
        description="Training", issue_date=date.today(), due_date=date.today(), status="sent",
        subtotal=Decimal("100.00"), tax_amount=Decimal("0"), total=Decimal("100.00"), currency="USD",
    )

    class Session:
        async def get(self, *_args, **_kwargs):
            return invoice

    async def claim(*_args, **_kwargs):
        return SimpleNamespace(claimed=True, record=object())

    async def paid(*_args, **_kwargs):
        return Decimal("95.00")

    async def fail(*_args, **_kwargs):
        pass

    monkeypatch.setattr(invoices.idempotency_service, "claim", claim)
    monkeypatch.setattr(invoices.idempotency_service, "fail", fail)
    monkeypatch.setattr(invoices, "_paid", paid)
    with pytest.raises(HTTPException) as error:
        await invoices.record_payment(
            Session(), org_id="org", invoice_id="inv", amount=Decimal("10.00"), method="cash",
            note=None, paid_on=None, actor_id="owner", idempotency_key="overpay-key",
        )
    assert error.value.status_code == 422
