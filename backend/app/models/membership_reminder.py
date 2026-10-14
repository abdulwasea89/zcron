"""Idempotency records for subscription renewal and grace reminders."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import UniqueConstraint
from sqlmodel import Field

from app.models.base import TimestampModel, UUIDModel, utcnow


class MembershipReminder(UUIDModel, TimestampModel, table=True):
    __tablename__ = "membership_reminders"
    __table_args__ = (
        UniqueConstraint(
            "subscription_id", "period_end", "stage", name="uq_membership_reminder_cycle_stage"
        ),
    )

    organization_id: str = Field(index=True, foreign_key="organizations.id")
    subscription_id: str = Field(index=True, foreign_key="subscriptions.id")
    period_end: datetime
    stage: str = Field(index=True)  # pre_expiry_7 / pre_expiry_3 / pre_expiry_1 / grace_1..3
    sent_at: datetime = Field(default_factory=utcnow)
