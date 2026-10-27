from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlmodel import Session, SQLModel, select

from app.core.constants import MemberStatus, PaymentMethod, PaymentStatus, Role
from app.integrations.stripe_connect import connect_stripe
from app.models.membership import OrganizationMember
from app.models.organization import Organization
from app.models.payment import Payment
from app.models.plan import MembershipPlan
from app.models.subscription import Subscription
from app.models.user import User
from app.services import (family_service, memberships_service, onboarding_service,
                          payments_service, referrals_service, webhook_service, winback_service)


class AsyncFacade:
    def __init__(self, db):
        self.db = db

    async def get(self, *args, **kwargs):
        return self.db.get(*args, **kwargs)

    async def execute(self, statement):
        return self.db.execute(statement)

    async def flush(self):
        self.db.flush()

    def add(self, row):
        self.db.add(row)


@pytest.fixture
def payment_db(monkeypatch):
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(payments_service, "record_audit", AsyncMock())
    monkeypatch.setattr(webhook_service, "record_audit", AsyncMock())
    with Session(engine) as db:
        db.add(Organization(id="gym", name="Gym", org_code="GYM", stripe_connect_account_id="acct_gym"))
        db.add(Payment(id="payment", organization_id="gym", method=PaymentMethod.CARD,
                       status=PaymentStatus.PENDING, amount=100, currency="USD", stripe_payment_intent_id="pi_1"))
        db.flush()
        yield db, AsyncFacade(db)
    engine.dispose()


def intent(status="succeeded", amount=10000, currency="usd"):
    return SimpleNamespace(id="pi_1", status=status, currency=currency, amount_received=amount,
                           charge_id="ch_1", payment_method_type="card", payment_method_id="pm_1")


async def test_verified_settlement_updates_record_and_is_audited(payment_db, monkeypatch):
    db, session = payment_db
    lookup = AsyncMock(return_value=intent())
    monkeypatch.setattr(connect_stripe, "inspect_member_intent", lookup)
    result = await payments_service.verify_card_payment(session, org_id="gym", payment_id="payment", actor_id="owner")
    assert result == {"payment_status": "succeeded", "provider_status": "succeeded"}
    assert db.get(Payment, "payment").status == PaymentStatus.SUCCEEDED
    assert lookup.await_args_list[0].kwargs == {"connected_account_id": "acct_gym", "intent_id": "pi_1"}
    assert payments_service.record_audit.await_args.kwargs["action"] == "payment.provider_verification"


async def test_verified_signup_activates_membership_once(payment_db, monkeypatch):
    db, session = payment_db
    db.add_all([
        User(id="user", email="member@example.test", hashed_password="unused"),
        OrganizationMember(id="member", organization_id="gym", user_id="user", role=Role.MEMBER,
                           member_status=MemberStatus.PENDING_PAYMENT),
        MembershipPlan(id="plan", organization_id="gym", name="Plan", price=100),
    ])
    payment = db.get(Payment, "payment")
    payment.member_id, payment.plan_id, payment.note = "member", "plan", "web_member_signup"
    db.flush()
    monkeypatch.setattr(connect_stripe, "inspect_member_intent", AsyncMock(return_value=intent()))
    monkeypatch.setattr(family_service, "sync_family_status", AsyncMock())
    monkeypatch.setattr(referrals_service, "qualify_referral_for_member", AsyncMock())
    monkeypatch.setattr(onboarding_service, "start_journey", AsyncMock())
    monkeypatch.setattr(winback_service, "mark_recovered", AsyncMock())
    monkeypatch.setattr(memberships_service, "record_audit", AsyncMock())
    monkeypatch.setattr(memberships_service, "send_email", AsyncMock())
    monkeypatch.setattr(memberships_service, "send_push", AsyncMock())
    monkeypatch.setattr(memberships_service.events, "membership_changed", AsyncMock())
    first = await payments_service.verify_card_payment(session, org_id="gym", payment_id="payment", actor_id="owner")
    second = await payments_service.verify_card_payment(session, org_id="gym", payment_id="payment", actor_id="owner")
    assert first["payment_status"] == second["payment_status"] == "succeeded"
    assert db.get(OrganizationMember, "member").member_status == MemberStatus.ACTIVE
    assert len(db.exec(select(Subscription)).all()) == 1


async def test_processing_payment_remains_pending(payment_db, monkeypatch):
    db, session = payment_db
    monkeypatch.setattr(connect_stripe, "inspect_member_intent", AsyncMock(return_value=intent(status="processing", amount=0)))
    result = await payments_service.verify_card_payment(session, org_id="gym", payment_id="payment", actor_id="owner")
    assert result == {"payment_status": "pending", "provider_status": "processing"}
    assert db.get(Payment, "payment").status == PaymentStatus.PENDING


@pytest.mark.parametrize("provider_result,expected", [(None, 503), (intent(amount=9999), 409), (intent(currency="eur"), 409)])
async def test_unverifiable_or_mismatched_settlement_remains_pending(payment_db, monkeypatch, provider_result, expected):
    db, session = payment_db
    monkeypatch.setattr(connect_stripe, "inspect_member_intent", AsyncMock(return_value=provider_result))
    with pytest.raises(HTTPException) as error:
        await payments_service.verify_card_payment(session, org_id="gym", payment_id="payment", actor_id="owner")
    assert error.value.status_code == expected
    assert db.get(Payment, "payment").status == PaymentStatus.PENDING


async def test_other_gym_cannot_verify_payment(payment_db, monkeypatch):
    _db, session = payment_db
    lookup = AsyncMock()
    monkeypatch.setattr(connect_stripe, "inspect_member_intent", lookup)
    with pytest.raises(HTTPException) as error:
        await payments_service.verify_card_payment(session, org_id="other", payment_id="payment", actor_id="owner")
    assert error.value.status_code == 404
    lookup.assert_not_awaited()
