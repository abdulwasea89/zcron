"""Subscription: a member's active plan within an org.

Snapshots the price at signup so later plan edits don't reprice existing members
(Section 6.7). Tracks cycle dates and grace/freeze windows (Section 9).
"""

from __future__ import annotations

from datetime import datetime

from sqlmodel import Field

from app.core.constants import SubscriptionStatus
from app.models.base import TimestampModel, UUIDModel, utcnow


class Subscription(UUIDModel, TimestampModel, table=True):
    __tablename__ = "subscriptions"

    organization_id: str = Field(index=True, foreign_key="organizations.id")
    member_id: str = Field(index=True, foreign_key="organization_members.id")
    plan_id: str = Field(foreign_key="membership_plans.id")

    status: SubscriptionStatus = Field(default=SubscriptionStatus.ACTIVE, index=True)

    # Legacy pricing preserved (Section: Database Core Schema -> Subscriptions)
    price_snapshot: float = 0.0
    currency: str = "USD"

    # Cycle / lifecycle windows
    started_at: datetime = Field(default_factory=utcnow)
    current_period_end: datetime | None = None
    grace_until: datetime | None = None
    frozen_until: datetime | None = None
    frozen_at: datetime | None = None
    status_before_freeze: SubscriptionStatus | None = None
    cancelled_at: datetime | None = None

    # For one-time packs: remaining class credits
    classes_remaining: int | None = None
    credits_allowance: int | None = None  # snapshot of plan allowance; null = unlimited

    stripe_subscription_id: str | None = None
