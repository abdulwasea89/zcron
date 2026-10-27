"""CashReconciliation: end-of-day cash count vs system total (Section 11.2)."""

from __future__ import annotations

from datetime import date

from sqlmodel import Field

from app.models.base import TimestampModel, UUIDModel


class CashReconciliation(UUIDModel, TimestampModel, table=True):
    __tablename__ = "cash_reconciliations"

    organization_id: str = Field(index=True, foreign_key="organizations.id")
    business_date: date = Field(index=True)
    currency: str | None = None
    opening_float: float = 0.0
    system_total: float = 0.0
    counted_total: float = 0.0
    discrepancy: float = 0.0
    performed_by: str = Field(foreign_key="users.id")
    notes: str | None = None
