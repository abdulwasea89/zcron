"""Payroll models: runs, per-staff entries, and advance requests (Section 15)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Column, Numeric

from sqlmodel import Field

from app.core.constants import AdvanceStatus, PayoutMethod, PayrollStatus
from app.models.base import TimestampModel, UUIDModel


class PayrollRun(UUIDModel, TimestampModel, table=True):
    __tablename__ = "payroll_runs"

    organization_id: str = Field(index=True, foreign_key="organizations.id")
    period_start: date
    period_end: date
    status: PayrollStatus = Field(default=PayrollStatus.DRAFT, index=True)
    total_gross: Decimal = Field(default=Decimal("0.00"), sa_column=Column(Numeric(14, 2), nullable=False))
    total_deductions: Decimal = Field(default=Decimal("0.00"), sa_column=Column(Numeric(14, 2), nullable=False))
    total_net: Decimal = Field(default=Decimal("0.00"), sa_column=Column(Numeric(14, 2), nullable=False))
    locked_at: datetime | None = None
    finalized_at: datetime | None = None
    paid_at: datetime | None = None
    created_by: str | None = Field(default=None, foreign_key="users.id")


class PayrollEntry(UUIDModel, TimestampModel, table=True):
    __tablename__ = "payroll_entries"

    organization_id: str = Field(index=True, foreign_key="organizations.id")
    payroll_run_id: str = Field(index=True, foreign_key="payroll_runs.id")
    staff_member_id: str = Field(index=True, foreign_key="organization_members.id")

    # Components (Section 15.1 / 15.3)
    fixed: Decimal = Field(default=Decimal("0.00"), sa_column=Column(Numeric(14, 2), nullable=False))
    hourly_amount: Decimal = Field(default=Decimal("0.00"), sa_column=Column(Numeric(14, 2), nullable=False))
    hours_worked: float = 0.0
    class_amount: Decimal = Field(default=Decimal("0.00"), sa_column=Column(Numeric(14, 2), nullable=False))
    classes_taught: int = 0
    commission_amount: Decimal = Field(default=Decimal("0.00"), sa_column=Column(Numeric(14, 2), nullable=False))
    bonus: Decimal = Field(default=Decimal("0.00"), sa_column=Column(Numeric(14, 2), nullable=False))
    deductions: Decimal = Field(default=Decimal("0.00"), sa_column=Column(Numeric(14, 2), nullable=False))
    advance_repayment: Decimal = Field(default=Decimal("0.00"), sa_column=Column(Numeric(14, 2), nullable=False))
    net: Decimal = Field(default=Decimal("0.00"), sa_column=Column(Numeric(14, 2), nullable=False))

    payout_method: PayoutMethod = Field(default=PayoutMethod.BANK_TRANSFER)
    paid_at: datetime | None = None
    payout_reference: str | None = None
    paid_amount: Decimal | None = Field(default=None, sa_column=Column(Numeric(14, 2), nullable=True))
    pay_stub_url: str | None = None
    notes: str | None = None
    trainer_confirmed: bool = False  # for cash payouts (Section 15.6)


class PayAdvance(UUIDModel, TimestampModel, table=True):
    __tablename__ = "pay_advances"

    organization_id: str = Field(index=True, foreign_key="organizations.id")
    staff_member_id: str = Field(index=True, foreign_key="organization_members.id")
    amount: Decimal = Field(default=Decimal("0.00"), sa_column=Column(Numeric(14, 2), nullable=False))
    status: AdvanceStatus = Field(default=AdvanceStatus.REQUESTED, index=True)
    repayment_per_period: Decimal = Field(default=Decimal("0.00"), sa_column=Column(Numeric(14, 2), nullable=False))
    repaid_amount: Decimal = Field(default=Decimal("0.00"), sa_column=Column(Numeric(14, 2), nullable=False))
    approved_by: str | None = Field(default=None, foreign_key="users.id")
    note: str | None = None
