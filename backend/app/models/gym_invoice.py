"""Member invoices and outstanding balances for gym operations."""

from datetime import date
from decimal import Decimal

from sqlalchemy import Column, Numeric, UniqueConstraint
from sqlmodel import Field

from app.models.base import TimestampModel, UUIDModel


class GymInvoice(UUIDModel, TimestampModel, table=True):
    __tablename__ = "gym_invoices"
    __table_args__ = (
        UniqueConstraint("organization_id", "invoice_number", name="uq_gym_invoices_org_number"),
    )

    organization_id: str = Field(index=True, foreign_key="organizations.id")
    member_id: str = Field(index=True, foreign_key="organization_members.id")
    invoice_number: str = Field(index=True)
    description: str
    issue_date: date
    due_date: date
    status: str = Field(default="draft", index=True)  # draft | sent | partial | paid | void
    subtotal: Decimal = Field(sa_column=Column(Numeric(14, 2), nullable=False))
    tax_amount: Decimal = Field(default=Decimal("0.00"), sa_column=Column(Numeric(14, 2), nullable=False))
    total: Decimal = Field(sa_column=Column(Numeric(14, 2), nullable=False))
    currency: str = Field(default="USD", max_length=3)
    notes: str | None = None
    email_accepted: bool = False
