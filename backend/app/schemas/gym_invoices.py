"""Admin schemas for member invoices and receivables."""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator


class GymInvoiceCreate(BaseModel):
    member_id: str
    description: str = Field(min_length=1, max_length=240)
    subtotal: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    tax_amount: Decimal = Field(default=Decimal("0.00"), ge=0, max_digits=12, decimal_places=2)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    due_date: date
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("currency")
    @classmethod
    def uppercase_currency(cls, value: str | None) -> str | None:
        return value.upper() if value else value


class GymInvoicePaymentCreate(BaseModel):
    amount: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    method: str = Field(pattern="^(cash|bank_transfer|mobile_wallet)$")
    note: str | None = Field(default=None, max_length=500)
    paid_on: date | None = None


class GymInvoiceOut(BaseModel):
    id: str
    invoice_number: str
    member_id: str
    member_name: str | None = None
    member_email: str | None = None
    description: str
    issue_date: date
    due_date: date
    status: str
    subtotal: Decimal
    tax_amount: Decimal
    total: Decimal
    paid_amount: Decimal
    balance_due: Decimal
    currency: str
    notes: str | None
    email_accepted: bool
