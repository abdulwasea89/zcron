"""Cash payment logging & end-of-day reconciliation schemas (Section 11)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

from app.core.constants import PaymentMethod


class CashPayerShare(BaseModel):
    member_id: str = Field(min_length=1, max_length=128)
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2, allow_inf_nan=False)


class CashPaymentLog(BaseModel):
    """Front-desk logs an offline payment for a member (Section 11.1)."""

    member_id: str
    plan_id: str
    amount: float
    method: PaymentMethod = PaymentMethod.CASH
    note: str | None = None
    promo_code: str | None = None
    payer_shares: list[CashPayerShare] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def validate_payer_shares(self):
        if self.payer_shares:
            if self.method not in {PaymentMethod.CASH, PaymentMethod.BANK_TRANSFER, PaymentMethod.MOBILE_WALLET}:
                raise ValueError("Family shares require an offline payment method.")
            ids = [share.member_id for share in self.payer_shares]
            if len(set(ids)) != len(ids):
                raise ValueError("Choose each payer only once.")
            if sum((share.amount for share in self.payer_shares), Decimal("0")) != Decimal(str(self.amount)):
                raise ValueError("Payer shares must add up to the full amount due.")
        return self


class CashQuoteRequest(BaseModel):
    member_id: str
    plan_id: str
    promo_code: str | None = None


class CashPaymentOut(BaseModel):
    payment_id: str
    member_id: str
    amount: float
    method: str
    member_status: str
    receipt_pdf_url: str | None = None


class CashHistoryOut(BaseModel):
    id: str
    member_name: str | None
    plan_name: str | None
    amount: float
    currency: str
    method: str
    status: str
    paid_at: datetime | None
    payer_shares: list[CashPayerShare] = []


class CashMemberOut(BaseModel):
    """Minimal member record for the cash-logging search box.

    Deliberately excludes directory fields (salaries, rates, etc.) that
    front-desk staff must not see.
    """

    member_id: str
    full_name: str | None = None
    email: str
    member_status: str
    role: str


class ReconciliationRequest(BaseModel):
    business_date: date
    counted_total: float
    notes: str | None = None


class ReconciliationOut(BaseModel):
    id: str
    business_date: date
    system_total: float
    counted_total: float
    discrepancy: float
    performed_by: str
    alert_triggered: bool = False
