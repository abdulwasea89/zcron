"""Member requests to change or end a membership plan (blueprint 15)."""

from __future__ import annotations

from datetime import datetime

from sqlmodel import Field

from app.models.base import TimestampModel, UUIDModel


class MembershipChangeRequest(UUIDModel, TimestampModel, table=True):
    __tablename__ = "membership_change_requests"

    organization_id: str = Field(index=True, foreign_key="organizations.id")
    member_id: str = Field(index=True, foreign_key="organization_members.id")
    subscription_id: str = Field(index=True, foreign_key="subscriptions.id")
    request_type: str = Field(index=True)  # upgrade | downgrade | transfer | cancel
    target_plan_id: str | None = Field(default=None, foreign_key="membership_plans.id")
    offer_type: str | None = None  # pause | alternate_plan | discount
    offer_plan_id: str | None = Field(default=None, foreign_key="membership_plans.id")
    offer_discount_percent: float | None = None
    offer_discount_months: int | None = None
    amount_due: float = 0.0
    vault_credit_minor: int = 0
    prepaid_before_minor: int | None = None
    payment_id: str | None = Field(default=None, foreign_key="payments.id")
    effective_at: datetime | None = None
    reason: str = Field(max_length=500)
    status: str = Field(default="pending", index=True)  # pending | offered | approved | rejected | withdrawn
    save_offer: str | None = Field(default=None, max_length=500)
    reviewed_by: str | None = Field(default=None, foreign_key="users.id")
    reviewed_at: datetime | None = None
    decision_note: str | None = Field(default=None, max_length=500)
