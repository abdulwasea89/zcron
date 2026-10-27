from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlmodel import Session, SQLModel

from app.core.constants import PaymentMethod, PaymentStatus, Role
from app.integrations.stripe_connect import connect_stripe
from app.models.organization import Organization
from app.models.payment import Payment
from app.services import memberships_service, webhook_service


class AsyncFacade:
    def __init__(self, db):
        self.db = db

    async def execute(self, statement):
        return self.db.execute(statement)

    async def get(self, *args, **kwargs):
        return self.db.get(*args, **kwargs)

    def add(self, row):
        self.db.add(row)


@pytest.fixture
def payment_db(monkeypatch):
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(connect_stripe, "inspect_member_intent", AsyncMock(return_value=None))
    monkeypatch.setattr(webhook_service, "record_audit", AsyncMock())
    with Session(engine) as db:
        db.add(Organization(id="gym", name="Gym", org_code="GYM", stripe_connect_account_id="acct_gym"))
        db.add(Payment(id="payment", organization_id="gym", method=PaymentMethod.CARD,
                       status=PaymentStatus.PENDING, amount=100.25, currency="USD", stripe_payment_intent_id="pi_1"))
        db.flush()
        yield db, AsyncFacade(db)
    engine.dispose()


@pytest.mark.parametrize("amount,currency,status", [(10024, "usd", "succeeded"),
    (10025, "eur", "succeeded"), (10025, "usd", "processing"), (None, "usd", "succeeded")])
async def test_success_event_must_match_settled_amount_and_currency(payment_db, amount, currency, status):
    db, session = payment_db
    with pytest.raises(HTTPException) as error:
        await webhook_service._connect_payment_succeeded(session, {
            "id": "pi_1", "amount_received": amount, "currency": currency, "status": status,
        }, "acct_gym")
    assert error.value.status_code == 409
    assert db.get(Payment, "payment").status == PaymentStatus.PENDING


async def test_failed_then_successful_payment_stays_successful_on_late_failure(payment_db):
    db, session = payment_db
    await webhook_service._connect_payment_failed(session, {"id": "pi_1"}, "acct_gym")
    assert db.get(Payment, "payment").status == PaymentStatus.FAILED
    await webhook_service._connect_payment_succeeded(session, {
        "id": "pi_1", "amount_received": 10025, "currency": "usd", "status": "succeeded",
    }, "acct_gym")
    assert db.get(Payment, "payment").status == PaymentStatus.SUCCEEDED
    await webhook_service._connect_payment_failed(session, {"id": "pi_1"}, "acct_gym")
    assert db.get(Payment, "payment").status == PaymentStatus.SUCCEEDED


@pytest.mark.parametrize("status", [PaymentStatus.REFUNDED, PaymentStatus.PARTIALLY_REFUNDED])
async def test_late_success_and_failure_do_not_undo_refunds(payment_db, status):
    db, session = payment_db
    payment = db.get(Payment, "payment")
    payment.status = status
    db.flush()
    await webhook_service._connect_payment_succeeded(session, {"id": "pi_1"}, "acct_gym")
    await webhook_service._connect_payment_failed(session, {"id": "pi_1"}, "acct_gym")
    assert payment.status == status


async def test_wrong_connected_account_cannot_settle_payment(payment_db):
    db, session = payment_db
    result = await webhook_service._connect_payment_succeeded(session, {
        "id": "pi_1", "amount_received": 10025, "currency": "usd", "status": "succeeded",
    }, "acct_other")
    assert result["reason"] == "connected account mismatch"
    assert db.get(Payment, "payment").status == PaymentStatus.PENDING


@pytest.mark.parametrize("status", [PaymentStatus.REFUNDED, PaymentStatus.PARTIALLY_REFUNDED])
async def test_signup_confirmation_does_not_restore_refunded_payment(payment_db, monkeypatch, status):
    db, session = payment_db
    payment = db.get(Payment, "payment")
    payment.member_id = "member"
    payment.note = "web_member_signup"
    payment.status = status
    db.flush()
    monkeypatch.setattr(memberships_service, "_member_for", AsyncMock(return_value=SimpleNamespace(id="member", role=Role.MEMBER)))
    with pytest.raises(HTTPException) as error:
        await memberships_service.confirm_web_signup_payment(session, org_id="gym", user_id="user", payment_intent_id="pi_1")
    assert error.value.status_code == 409
    assert payment.status == status
    connect_stripe.inspect_member_intent.assert_not_awaited()
