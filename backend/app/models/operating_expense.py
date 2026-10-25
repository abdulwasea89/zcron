"""Owner-entered operating expenses for gym cash-flow tracking."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Column, Numeric
from sqlmodel import Field

from app.models.base import TimestampModel, UUIDModel


class OperatingExpense(UUIDModel, TimestampModel, table=True):
    __tablename__ = "operating_expenses"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_operating_expenses_positive_amount"),
        CheckConstraint("length(currency) = 3", name="ck_operating_expenses_currency_length"),
    )

    organization_id: str = Field(index=True, foreign_key="organizations.id")
    category: str = Field(index=True)
    description: str
    vendor: str | None = None
    amount: Decimal = Field(sa_column=Column(Numeric(14, 2), nullable=False))
    currency: str = Field(index=True, max_length=3)
    incurred_on: date = Field(index=True)
    created_by: str = Field(foreign_key="users.id")
    voided_at: datetime | None = None
    voided_by: str | None = Field(default=None, foreign_key="users.id")
    void_reason: str | None = None
