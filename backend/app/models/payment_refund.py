"""Dated refund movements, separate from payment lifetime refund totals."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Column, Numeric
from sqlmodel import Field

from app.models.base import TimestampModel, UUIDModel, utcnow


class PaymentRefund(UUIDModel, TimestampModel, table=True):
    __tablename__ = "payment_refunds"
    __table_args__ = (CheckConstraint("amount > 0", name="ck_payment_refund_positive"),)

    organization_id: str = Field(index=True, foreign_key="organizations.id")
    payment_id: str = Field(index=True, foreign_key="payments.id")
    amount: Decimal = Field(sa_column=Column(Numeric(14, 2), nullable=False))
    currency: str = Field(index=True)
    occurred_at: datetime = Field(default_factory=utcnow, index=True)
    source: str
    actor_user_id: str | None = Field(default=None, foreign_key="users.id")
