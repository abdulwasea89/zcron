"""Gym operating-expense inputs and ledger outputs."""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

ExpenseCategory = Literal[
    "rent", "payroll", "utilities", "equipment", "marketing", "maintenance", "supplies", "other",
]


class ExpenseCreate(BaseModel):
    category: ExpenseCategory
    description: str = Field(min_length=1, max_length=300)
    vendor: str | None = Field(default=None, max_length=160)
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    currency: str | None = None
    incurred_on: date

    @field_validator("description")
    @classmethod
    def strip_description(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Description is required.")
        return cleaned

    @field_validator("vendor")
    @classmethod
    def strip_vendor(cls, value: str | None) -> str | None:
        cleaned = value.strip() if value else ""
        return cleaned or None

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str | None) -> str | None:
        if value is None:
            return None
        currency = value.strip().upper()
        if not re.fullmatch(r"[A-Z]{3}", currency):
            raise ValueError("Currency must be a three-letter code.")
        return currency


class ExpenseVoid(BaseModel):
    reason: str = Field(min_length=3, max_length=300)

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, value: str) -> str:
        reason = value.strip()
        if len(reason) < 3:
            raise ValueError("Give a short reason for voiding this expense.")
        return reason


class ExpenseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    category: str
    description: str
    vendor: str | None
    amount: Decimal
    currency: str
    incurred_on: date
    created_by: str
    created_at: datetime
    voided_at: datetime | None
    void_reason: str | None

    @field_serializer("amount", when_used="json")
    def serialize_amount(self, value: Decimal) -> str:
        return format(value, ".2f")


class ExpenseListOut(BaseModel):
    items: list[ExpenseOut]
    totals_by_currency: dict[str, str]
