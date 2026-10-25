"""Referral program and reward API schemas."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class ReferralProgramUpdate(BaseModel):
    enabled: bool
    reward_description: str = Field(min_length=3, max_length=200)
    reward_amount: Decimal = Field(default=Decimal("0.00"), ge=0, le=100000, max_digits=8, decimal_places=2)


class ReferralProgramOut(BaseModel):
    enabled: bool
    reward_description: str
    reward_amount: Decimal = Decimal("0.00")
    reward_currency: str = "USD"


class ReferralAdminItem(BaseModel):
    id: str
    referrer_name: str
    referrer_email: str
    referred_name: str
    referred_email: str
    status: str
    reward_description: str
    qualified_at: datetime | None
    rewards: list[dict]


class ReferralAdminOverview(BaseModel):
    program: ReferralProgramOut
    referrals: list[ReferralAdminItem]
    pending_rewards: int
    qualified_count: int


class MemberReferralItem(BaseModel):
    id: str
    referred_name: str | None
    status: str
    reward_description: str
    created_at: datetime


class MemberReferralOverview(BaseModel):
    enabled: bool
    code: str | None
    organization_code: str
    reward_description: str
    referrals: list[MemberReferralItem]
    earned_rewards: list[dict]


class ReferralRewardOut(BaseModel):
    id: str
    description: str
    status: str
    earned_at: datetime
    fulfilled_at: datetime | None
    amount_minor: int = 0
    currency: str = "USD"
