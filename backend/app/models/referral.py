"""Referral program settings, member codes, conversions, and rewards."""

from __future__ import annotations

from datetime import datetime

from sqlmodel import Field, UniqueConstraint

from app.models.base import TimestampModel, UUIDModel, utcnow


class ReferralProgram(UUIDModel, TimestampModel, table=True):
    __tablename__ = "referral_programs"

    organization_id: str = Field(index=True, unique=True, foreign_key="organizations.id")
    enabled: bool = False
    reward_description: str = "A referral reward"
    reward_amount_minor: int = 0
    reward_currency: str = "USD"
    updated_by: str | None = Field(default=None, foreign_key="users.id")


class ReferralCode(UUIDModel, TimestampModel, table=True):
    __tablename__ = "referral_codes"
    __table_args__ = (
        UniqueConstraint("organization_id", "member_id", name="uq_referral_code_member"),
        UniqueConstraint("organization_id", "code", name="uq_referral_code_org_code"),
    )

    organization_id: str = Field(index=True, foreign_key="organizations.id")
    member_id: str = Field(index=True, foreign_key="organization_members.id")
    code: str = Field(index=True)


class Referral(UUIDModel, TimestampModel, table=True):
    __tablename__ = "referrals"
    __table_args__ = (
        UniqueConstraint("referred_member_id", name="uq_referral_referred_member"),
    )

    organization_id: str = Field(index=True, foreign_key="organizations.id")
    referral_code_id: str = Field(index=True, foreign_key="referral_codes.id")
    referrer_member_id: str = Field(index=True, foreign_key="organization_members.id")
    referred_member_id: str = Field(index=True, foreign_key="organization_members.id")
    status: str = Field(default="pending", index=True)
    reward_description: str = "A referral reward"
    qualified_at: datetime | None = None


class ReferralReward(UUIDModel, TimestampModel, table=True):
    __tablename__ = "referral_rewards"
    __table_args__ = (
        UniqueConstraint("referral_id", "recipient_member_id", name="uq_referral_reward_recipient"),
    )

    organization_id: str = Field(index=True, foreign_key="organizations.id")
    referral_id: str = Field(index=True, foreign_key="referrals.id")
    recipient_member_id: str = Field(index=True, foreign_key="organization_members.id")
    description: str
    amount_minor: int = 0
    currency: str = "USD"
    status: str = Field(default="earned", index=True)
    earned_at: datetime = Field(default_factory=utcnow)
    fulfilled_at: datetime | None = None
    fulfilled_by: str | None = Field(default=None, foreign_key="users.id")
