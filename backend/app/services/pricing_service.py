"""One quote for card checkout and offline membership payments.

The joining fee is charged on the first successful member payment. Promotions
discount the plan price only; tax applies after the discount and includes the
joining fee. All calculations use cents to avoid float drift.
"""

from decimal import Decimal, ROUND_HALF_UP

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.constants import PaymentKind, PaymentStatus, TaxMode
from app.core.security import now_utc
from app.models.payment import Payment
from app.models.plan import MembershipPlan
from app.models.promotion import Promotion
from app.schemas.promotions import PriceQuoteOut


def _cents(value: float) -> int:
    return int((Decimal(str(value)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def tax_totals(subtotal: int, rate: float, mode: TaxMode) -> tuple[int, int]:
    """Return total and tax in cents; inclusive tax stays inside the quoted price."""
    fraction = Decimal(str(rate))
    if not fraction.is_finite() or not 0 <= fraction <= 1 or subtotal < 0 or mode not in {TaxMode.ADDED, TaxMode.INCLUSIVE}:
        raise HTTPException(status_code=422, detail="Plan tax settings are invalid.")
    tax = int((Decimal(subtotal) * fraction / (1 + fraction if mode == TaxMode.INCLUSIVE else 1)).quantize(
        Decimal("1"), rounding=ROUND_HALF_UP,
    ))
    return (subtotal + tax if mode == TaxMode.ADDED else subtotal), tax


async def quote_member_payment(
    session: AsyncSession, *, org_id: str, member_id: str, plan: MembershipPlan,
    promo_code: str | None = None,
) -> PriceQuoteOut:
    if plan.organization_id != org_id:
        raise HTTPException(status_code=404, detail="Plan not found.")
    price = _cents(plan.price)
    if price < 0 or _cents(plan.joining_fee) < 0:
        raise HTTPException(status_code=422, detail="Plan pricing is invalid.")
    prior = (await session.execute(select(Payment.id).where(
        Payment.organization_id == org_id,
        Payment.member_id == member_id,
        Payment.kind == PaymentKind.MEMBER_FEE,
        Payment.status.in_([PaymentStatus.SUCCEEDED, PaymentStatus.PARTIALLY_REFUNDED, PaymentStatus.REFUNDED]),
    ).limit(1))).first()
    first_purchase = prior is None
    joining = _cents(plan.joining_fee) if first_purchase else 0
    discount = 0
    normalized = promo_code.strip().upper() if promo_code else None
    if normalized:
        promo = (await session.execute(select(Promotion).where(
            Promotion.organization_id == org_id, Promotion.code == normalized,
        ))).scalar_one_or_none()
        now = now_utc()
        if (promo is None or not promo.active or
            (promo.plan_id is not None and promo.plan_id != plan.id) or
            (promo.starts_at is not None and promo.starts_at > now) or
            (promo.ends_at is not None and promo.ends_at <= now)):
            raise HTTPException(status_code=422, detail="Promo code is invalid or expired.")
        discount = (
            int((Decimal(price) * Decimal(str(promo.discount_value)) / 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
            if promo.discount_type == "percent" else _cents(promo.discount_value)
        )
        discount = min(price, discount)
    subtotal = price + joining - discount
    total, tax = tax_totals(subtotal, plan.tax_rate, plan.tax_mode)
    return PriceQuoteOut(
        plan_price=price / 100, joining_fee=joining / 100,
        discount_amount=discount / 100, tax_amount=tax / 100,
        total=total / 100, currency=plan.currency, tax_included=plan.tax_mode == TaxMode.INCLUSIVE,
        promo_code=normalized, first_purchase=first_purchase,
    )
