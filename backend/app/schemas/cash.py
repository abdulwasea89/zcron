"""Cash payment logging & end-of-day reconciliation schemas (Section 11)."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel

from app.core.constants import PaymentMethod


class CashPaymentLog(BaseModel):
    """Front-desk logs an offline payment for a member (Section 11.1)."""

    member_id: str
    plan_id: str
    amount: float
    method: PaymentMethod = PaymentMethod.CASH
    note: str | None = None
    promo_code: str | None = None


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
