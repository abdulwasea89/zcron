"""Payroll schemas (Section 15)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field

from app.core.constants import PayoutMethod


class PayrollRunCreate(BaseModel):
    period_start: date
    period_end: date


class PayrollEntryOut(BaseModel):
    id: str
    staff_member_id: str
    fixed: Decimal
    hourly_amount: Decimal
    hours_worked: float
    class_amount: Decimal
    classes_taught: int
    commission_amount: Decimal
    bonus: Decimal
    deductions: Decimal
    advance_repayment: Decimal
    net: Decimal
    payout_method: str
    pay_stub_url: str | None
    notes: str | None


class PayrollRunOut(BaseModel):
    id: str
    period_start: date
    period_end: date
    status: str
    total_gross: Decimal
    total_deductions: Decimal
    total_net: Decimal
    entries: list[PayrollEntryOut] = []


class EntryAdjust(BaseModel):
    """Each manual change requires a note (audit trail, Section 15.2)."""

    bonus: Decimal | None = Field(default=None, max_digits=14, decimal_places=2, ge=0)
    deductions: Decimal | None = Field(default=None, max_digits=14, decimal_places=2, ge=0)
    payout_method: PayoutMethod | None = None
    note: str


class AdvanceRequest(BaseModel):
    amount: Decimal = Field(max_digits=14, decimal_places=2, gt=0)
    repayment_per_period: Decimal = Field(max_digits=14, decimal_places=2, gt=0)


class AdvanceDecision(BaseModel):
    approve: bool
    repayment_per_period: Decimal | None = Field(default=None, max_digits=14, decimal_places=2, gt=0)


class AdvanceOut(BaseModel):
    id: str
    staff_member_id: str
    amount: Decimal
    status: str
    repayment_per_period: Decimal
    repaid_amount: Decimal
