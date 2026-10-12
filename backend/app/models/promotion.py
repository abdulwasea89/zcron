"""Tenant-owned promo codes for a membership plan or the whole gym."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import UniqueConstraint
from sqlmodel import Field

from app.models.base import TimestampModel, UUIDModel


class Promotion(UUIDModel, TimestampModel, table=True):
    __tablename__ = "promotions"
    __table_args__ = (UniqueConstraint("organization_id", "code", name="uq_promotions_org_code"),)

    organization_id: str = Field(index=True, foreign_key="organizations.id")
    plan_id: str | None = Field(default=None, foreign_key="membership_plans.id")
    code: str = Field(index=True)
    discount_type: str  # percent | fixed
    discount_value: float
    active: bool = True
    starts_at: datetime | None = None
    ends_at: datetime | None = None
