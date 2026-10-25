from decimal import Decimal
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.core.constants import PaymentMethod, PaymentStatus
from app.models.organization import Organization
from app.models.payment import Payment
from app.models.payment_refund import PaymentRefund
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
