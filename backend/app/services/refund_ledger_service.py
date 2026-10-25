"""Record refund movements while the caller holds the payment row lock."""

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.payment import Payment
from app.models.payment_refund import PaymentRefund


async def record_refund(session: AsyncSession, *, payment: Payment, amount: Decimal,
                        source: str, actor_id: str | None = None) -> None:
    if not amount.is_finite() or amount <= 0:
        raise ValueError("Refund movement must be a positive finite amount.")
    amount = amount.quantize(Decimal("0.01"))
    if amount <= 0:
        raise ValueError("Refund movement must be at least one minor unit.")
    if payment.refunded_amount:
        existing = (await session.execute(select(PaymentRefund.id).where(
            PaymentRefund.organization_id == payment.organization_id,
            PaymentRefund.payment_id == payment.id,
        ).limit(1))).scalar_one_or_none()
        if existing is None:
            session.add(PaymentRefund(
                organization_id=payment.organization_id, payment_id=payment.id,
                amount=Decimal(str(payment.refunded_amount)).quantize(Decimal("0.01")),
                currency=payment.currency, occurred_at=payment.refunded_at or payment.updated_at,
                source="legacy_snapshot",
            ))
    session.add(PaymentRefund(
        organization_id=payment.organization_id, payment_id=payment.id,
        amount=amount, currency=payment.currency, source=source, actor_user_id=actor_id,
    ))
