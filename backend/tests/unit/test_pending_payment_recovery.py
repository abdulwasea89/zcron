from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlmodel import select

import app.db.base  # noqa: F401
from app.core.constants import PaymentMethod, PaymentStatus
from app.integrations.stripe_connect import connect_stripe
from app.models.organization import Organization
from app.models.payment import Payment
from app.services import payments_service, webhook_service
from app.workers.celery_app import celery_app
from app.workers.pending_payment_recovery import recover_pending_payments


@pytest.fixture
async def pending_payment_rows(db):
    now = datetime(2026, 10, 28, 12)
    db.add(Organization(id="gym", name="Gym", org_code="GYM", stripe_connect_account_id="acct_gym"))
    for payment_id, intent_id, created_at in (
        ("paid", "pi_paid", now - timedelta(hours=1)),
        ("processing", "pi_processing", now - timedelta(hours=1)),
        ("mismatch", "pi_mismatch", now - timedelta(hours=1)),
        ("fresh", "pi_fresh", now - timedelta(minutes=5)),
        ("no-intent", None, now - timedelta(hours=1)),
    ):
        db.add(
            Payment(
                id=payment_id,
                organization_id="gym",
                method=PaymentMethod.CARD,
                status=PaymentStatus.PENDING,
                amount=100,
                currency="USD",
                stripe_payment_intent_id=intent_id,
                created_at=created_at,
                updated_at=created_at,
            )
        )
    await db.commit()
    return now


async def test_recovery_settles_only_verified_payment_and_backs_off(
    db,
    session_maker,
    pending_payment_rows,
    monkeypatch,
):
    now = pending_payment_rows
    monkeypatch.setattr(connect_stripe, "live", True)

    async def inspect(*, connected_account_id, intent_id):
        assert connected_account_id == "acct_gym"
        statuses = {
            "pi_paid": ("succeeded", 10000, "usd"),
            "pi_processing": ("processing", 0, "usd"),
            "pi_mismatch": ("succeeded", 9900, "usd"),
        }
        status, amount, currency = statuses[intent_id]
        return SimpleNamespace(
            id=intent_id,
            status=status,
            amount_received=amount,
            currency=currency,
            charge_id="ch_paid" if intent_id == "pi_paid" else None,
            payment_method_type="card",
            payment_method_id="pm_1",
        )

    monkeypatch.setattr(connect_stripe, "inspect_member_intent", inspect)
    monkeypatch.setattr(payments_service, "record_audit", AsyncMock())
    monkeypatch.setattr(webhook_service, "record_audit", AsyncMock())

    first = await recover_pending_payments(session_maker, now=now)
    assert first == {"checked": 3, "settled": 1, "pending": 1, "errors": 1}

    rows = {row.id: row for row in (await db.execute(select(Payment))).scalars()}
    assert rows["paid"].status == PaymentStatus.SUCCEEDED
    assert rows["processing"].status == PaymentStatus.PENDING
    assert rows["mismatch"].status == PaymentStatus.PENDING
    assert rows["paid"].provider_checked_at == now
    assert rows["processing"].provider_checked_at == now
    assert rows["mismatch"].provider_checked_at == now
    assert rows["fresh"].provider_checked_at is None
    assert rows["no-intent"].provider_checked_at is None

    assert await recover_pending_payments(session_maker, now=now + timedelta(minutes=4)) == {
        "checked": 0,
        "settled": 0,
        "pending": 0,
        "errors": 0,
    }


async def test_recovery_is_disabled_without_live_provider(session_maker, monkeypatch):
    monkeypatch.setattr(connect_stripe, "live", False)
    assert await recover_pending_payments(session_maker) == {
        "checked": 0,
        "settled": 0,
        "pending": 0,
        "errors": 0,
    }
    assert "verify-pending-payments" in celery_app.conf.beat_schedule
