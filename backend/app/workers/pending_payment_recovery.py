"""Recheck recorded pending Stripe intents without inferring unknown outcomes."""

from datetime import timedelta
import logging

from sqlalchemy import or_
from sqlmodel import select

from app.core.constants import PaymentKind, PaymentMethod, PaymentStatus
from app.core.security import now_utc
from app.db.session import async_session_maker
from app.integrations.stripe_connect import connect_stripe
from app.models.organization import Organization
from app.models.payment import Payment
from app.services.payments_service import verify_card_payment

MINIMUM_AGE = timedelta(minutes=10)
RECHECK_INTERVAL = timedelta(minutes=30)
BATCH_SIZE = 100


async def recover_pending_payments(session_factory=async_session_maker, *, now=None) -> dict:
    """Verify old recorded intents in small batches with independent transactions."""
    result = {"checked": 0, "settled": 0, "pending": 0, "errors": 0}
    if not connect_stripe.live:
        return result
    now = now or now_utc()
    async with session_factory() as session:
        candidates = (
            await session.execute(
                select(Payment.id, Payment.organization_id)
                .join(
                    Organization,
                    Organization.id == Payment.organization_id,
                )
                .where(
                    Payment.kind == PaymentKind.MEMBER_FEE,
                    Payment.method == PaymentMethod.CARD,
                    Payment.status == PaymentStatus.PENDING,
                    Payment.stripe_payment_intent_id.is_not(None),
                    Organization.stripe_connect_account_id.is_not(None),
                    Payment.created_at <= now - MINIMUM_AGE,
                    or_(
                        Payment.provider_checked_at.is_(None),
                        Payment.provider_checked_at <= now - RECHECK_INTERVAL,
                    ),
                )
                .order_by(Payment.provider_checked_at.asc().nullsfirst(), Payment.created_at.asc())
                .limit(BATCH_SIZE)
            )
        ).all()
    for payment_id, org_id in candidates:
        try:
            outcome_key = None
            checked = False
            async with session_factory.begin() as session:
                payment = (
                    await session.execute(
                        select(Payment)
                        .where(
                            Payment.id == payment_id,
                            Payment.organization_id == org_id,
                            Payment.status == PaymentStatus.PENDING,
                            or_(
                                Payment.provider_checked_at.is_(None),
                                Payment.provider_checked_at <= now - RECHECK_INTERVAL,
                            ),
                        )
                        .with_for_update(skip_locked=True)
                    )
                ).scalar_one_or_none()
                if payment is None:
                    continue
                payment.provider_checked_at = now
                session.add(payment)
                await session.flush()
                checked = True
                try:
                    async with session.begin_nested():
                        outcome = await verify_card_payment(
                            session, org_id=org_id, payment_id=payment_id, actor_id=None
                        )
                    outcome_key = (
                        "settled" if outcome["payment_status"] == "succeeded" else "pending"
                    )
                except Exception:  # one provider or fulfillment failure must not stop the batch
                    outcome_key = "errors"
                    logging.warning(
                        "Pending payment verification failed for payment %s", payment_id
                    )
            if outcome_key:
                if checked:
                    result["checked"] += 1
                result[outcome_key] += 1
        except Exception:
            if checked:
                result["checked"] += 1
            result["errors"] += 1
            logging.warning("Pending payment transaction failed for payment %s", payment_id)
    return result
