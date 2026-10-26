from decimal import Decimal
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.core.constants import PaymentKind, PaymentMethod, PaymentStatus
from app.core.security import now_utc
from app.models.organization import Organization
from app.models.payment import Payment
from app.models.payment_refund import PaymentRefund
from app.models.gym_invoice import GymInvoice
from app.schemas.payments import RefundRequest
from app.services import payments_service, refund_ledger_service, webhook_service


@pytest.mark.parametrize("amount", [0, -1, float("nan"), float("inf")])
def test_refund_inputs_reject_nonpositive_or_nonfinite_amounts(amount):
    with pytest.raises(ValidationError):
        RefundRequest(payment_id="payment", amount=amount)


@pytest.mark.asyncio
async def test_recording_new_refund_preserves_legacy_balance_without_repeating_baseline():
    payment = Payment(organization_id="org", amount=100, refunded_amount=25)
    added = []

    async def execute(_statement):
        return SimpleNamespace(scalar_one_or_none=lambda: "existing" if added else None)

    session = SimpleNamespace(execute=execute, add=added.append)
    await refund_ledger_service.record_refund(session, payment=payment, amount=Decimal("10.20"), source="admin")
    await refund_ledger_service.record_refund(session, payment=payment, amount=Decimal("5.00"), source="admin")
    assert [(row.source, row.amount) for row in added] == [
        ("legacy_snapshot", Decimal("25.00")), ("admin", Decimal("10.20")), ("admin", Decimal("5.00")),
    ]


@pytest.mark.asyncio
async def test_refund_holds_payment_lock_and_creates_one_ledger_movement(monkeypatch):
    payment = Payment(organization_id="org", amount=100, method=PaymentMethod.CASH, status=PaymentStatus.SUCCEEDED)
    added = []

    async def get(model, _id, **kwargs):
        assert model is Payment and kwargs["with_for_update"] is True
        return payment

    async def claim(*_args, **_kwargs):
        return SimpleNamespace(claimed=True, record=object())

    async def noop(*_args, **_kwargs):
        pass

    monkeypatch.setattr(payments_service.idempotency_service, "claim", claim)
    monkeypatch.setattr(payments_service.idempotency_service, "complete", noop)
    monkeypatch.setattr(payments_service, "record_audit", noop)
    await payments_service.refund(SimpleNamespace(get=get, add=added.append), org_id="org", payment_id=payment.id,
                                  amount=20.15, reason="requested", idempotency_key="key", actor_id="owner")
    movements = [row for row in added if isinstance(row, PaymentRefund)]
    assert len(movements) == 1 and movements[0].amount == Decimal("20.15")
    assert payment.refunded_amount == 20.15


@pytest.mark.asyncio
async def test_refund_reopens_member_invoice_balance(monkeypatch):
    payment = Payment(
        id="payment", organization_id="org", kind=PaymentKind.MEMBER_FEE,
        method=PaymentMethod.CASH, status=PaymentStatus.SUCCEEDED, amount=100,
        gym_invoice_id="invoice",
    )
    invoice = GymInvoice(
        id="invoice", organization_id="org", member_id="member", invoice_number="GINV-1",
        description="Training", issue_date=now_utc().date(), due_date=now_utc().date(),
        status="paid", subtotal=100, tax_amount=0, total=100, currency="USD",
    )
    audits = []

    class Session:
        async def get(self, model, *_args, **_kwargs):
            return payment if model is Payment else invoice

        def add(self, _row):
            pass

        async def flush(self):
            pass

    async def claim(*_args, **_kwargs):
        return SimpleNamespace(claimed=True, record=SimpleNamespace())

    async def record(*_args, **_kwargs):
        pass

    async def paid(*_args, **_kwargs):
        return Decimal("70.00")

    async def audit(*_args, **kwargs):
        audits.append(kwargs)

    async def complete(*_args, **_kwargs):
        pass

    monkeypatch.setattr(payments_service.idempotency_service, "claim", claim)
    monkeypatch.setattr(payments_service.idempotency_service, "complete", complete)
    monkeypatch.setattr("app.services.refund_ledger_service.record_refund", record)
    monkeypatch.setattr("app.services.gym_invoices_service._paid", paid)
    monkeypatch.setattr(payments_service, "record_audit", audit)
    monkeypatch.setattr("app.services.gym_invoices_service.record_audit", audit)
    await payments_service.refund(
        Session(), org_id="org", payment_id=payment.id, amount=30, reason="Return",
        idempotency_key="refund-invoice", actor_id="owner",
    )
    assert payment.status == PaymentStatus.PARTIALLY_REFUNDED
    assert invoice.status == "partial"
    assert any(row["action"] == "gym_invoice.balance_reopened" for row in audits)


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_amount", [1000, 3000])
async def test_out_of_order_or_duplicate_stripe_refunds_cannot_lower_recorded_refunds(monkeypatch, provider_amount):
    payment = Payment(organization_id="org", amount=100, refunded_amount=30)
    org = Organization(id="org", name="Gym", stripe_connect_account_id="acct")

    async def execute(query):
        assert "FOR UPDATE" in str(query)
        return SimpleNamespace(scalar_one_or_none=lambda: payment)

    async def get(*_args):
        return org

    async def noop(*_args, **_kwargs):
        pass

    monkeypatch.setattr(webhook_service, "record_audit", noop)
    await webhook_service._connect_charge_refunded(SimpleNamespace(execute=execute, get=get),
        {"id": "ch", "amount_refunded": provider_amount}, "acct")
    assert payment.refunded_amount == 30
