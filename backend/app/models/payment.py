"""Payment: every money event (Section: Database Core Schema -> Payments).

Covers card, cash, bank transfer, mobile wallet. Card payments carry Stripe IDs;
cash carries ``logged_by``. Every payment references the idempotency key that
created it (Section 13).
"""

from __future__ import annotations

from datetime import datetime

from sqlmodel import Field
from sqlalchemy import Column, JSON

from app.core.constants import PaymentKind, PaymentMethod, PaymentStatus
from app.models.base import TimestampModel, UUIDModel


class Payment(UUIDModel, TimestampModel, table=True):
    __tablename__ = "payments"

    organization_id: str = Field(index=True, foreign_key="organizations.id")
    member_id: str | None = Field(default=None, foreign_key="organization_members.id")
    subscription_id: str | None = Field(default=None, foreign_key="subscriptions.id")
    plan_id: str | None = Field(default=None, foreign_key="membership_plans.id")

    kind: PaymentKind = Field(default=PaymentKind.MEMBER_FEE, index=True)
    method: PaymentMethod = Field(default=PaymentMethod.CARD)
    status: PaymentStatus = Field(default=PaymentStatus.PENDING, index=True)

    amount: float = 0.0
    tax_amount: float = 0.0
    tax_included: bool = False
    plan_price_amount: float | None = None
    joining_fee_amount: float = 0.0
    discount_amount: float = 0.0
    promo_code: str | None = None
    currency: str = "USD"

    # Card via Stripe (Connect for member fees)
    stripe_payment_intent_id: str | None = Field(default=None, index=True)
    stripe_charge_id: str | None = None
    stripe_payment_method_type: str | None = None
    stripe_payment_method_id: str | None = None
    stripe_failure_code: str | None = None
    stripe_failure_decline_code: str | None = None
    recurring_consent: bool = False

    # Cash / offline
    logged_by: str | None = Field(default=None, foreign_key="users.id")
    note: str | None = None
    payer_contributions: list[dict] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))

    # Refunds
    refunded_amount: float = 0.0
    refunded_at: datetime | None = None

    # Idempotency linkage (Section 13)
    idempotency_key: str | None = Field(default=None, index=True)

    # Receipt linkage when activated via uploaded receipt
    receipt_id: str | None = Field(default=None, foreign_key="receipt_uploads.id")

    # Office vertical: settlement of a B2B invoice (kind=SPACE, method=bank_transfer|cash).
    invoice_id: str | None = Field(default=None, foreign_key="invoices.id", index=True)

    paid_at: datetime | None = None

    vault_credited_minor: int = 0  # already converted to credit; cannot also be refunded
