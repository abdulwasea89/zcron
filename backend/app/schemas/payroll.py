"""Payroll schemas (Section 15)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_serializer, field_validator

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
    paid_at: datetime | None = None
    payout_reference: str | None = None
    paid_amount: Decimal | None = None
    pay_stub_url: str | None
    notes: str | None

    @field_serializer(
        "fixed", "hourly_amount", "class_amount", "commission_amount", "bonus",
        "deductions", "advance_repayment", "net", "paid_amount", when_used="json"
    )
    def _serialize_money(self, value: Decimal | None) -> float | None:
        return float(value) if value is not None else None


class PayrollRunOut(BaseModel):
    id: str
    period_start: date
    period_end: date
    status: str
    total_gross: Decimal
    total_deductions: Decimal
    total_net: Decimal
    entries: list[PayrollEntryOut] = []

    @field_serializer("total_gross", "total_deductions", "total_net", when_used="json")
    def _serialize_money(self, value: Decimal) -> float:
        return float(value)


class MyPayStatementOut(BaseModel):
    payroll_run_id: str
    period_start: date
    period_end: date
    run_status: str
    paid_at: datetime | None
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
    entry_paid_at: datetime | None = None
    payout_reference: str | None = None
    paid_amount: Decimal | None = None

    @field_serializer(
        "fixed", "hourly_amount", "class_amount", "commission_amount", "bonus",
        "deductions", "advance_repayment", "net", "paid_amount", when_used="json"
    )
    def _serialize_money(self, value: Decimal | None) -> float | None:
        return float(value) if value is not None else None


class EntryAdjust(BaseModel):
    """Each manual change requires a note (audit trail, Section 15.2)."""

    bonus: Decimal | None = Field(default=None, max_digits=14, decimal_places=2, ge=0)
    deductions: Decimal | None = Field(default=None, max_digits=14, decimal_places=2, ge=0)
    payout_method: PayoutMethod | None = None
    note: str


class PayoutReconcile(BaseModel):
    payout_reference: str = Field(min_length=2, max_length=120)
    paid_amount: Decimal = Field(ge=0, max_digits=14, decimal_places=2)

    @field_validator("payout_reference")
    @classmethod
    def nonblank_reference(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 2:
            raise ValueError("Enter the bank, wallet, or cash receipt reference.")
        return value


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

    @field_serializer("amount", "repayment_per_period", "repaid_amount", when_used="json")
    def _serialize_money(self, value: Decimal) -> float:
        return float(value)
