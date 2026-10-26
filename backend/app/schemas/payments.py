"""Payment history & refund schemas (Sections 13, decisions)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class PaymentOut(BaseModel):
    id: str
    member_id: str | None
    plan_id: str | None
    kind: str
    method: str
    stripe_payment_method_type: str | None = None
    status: str
    amount: float
    tax_amount: float
    tax_included: bool = False
    plan_price_amount: float | None = None
    joining_fee_amount: float = 0.0
    discount_amount: float = 0.0
    promo_code: str | None = None
    currency: str
    refunded_amount: float
    paid_at: datetime | None
    created_at: datetime


class RefundRequest(BaseModel):
    payment_id: str
    amount: float | None = Field(default=None, gt=0, allow_inf_nan=False)  # None = full refund
    reason: str | None = None


class RefundOut(BaseModel):
    payment_id: str
    status: str
    refunded_amount: float
