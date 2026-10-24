"""Win-back schemas (#36)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class LapsedMemberOut(BaseModel):
    member_id: str
    name: str | None = None
    email: str
    status: str
    last_visit_at: datetime | None = None
    days_since_last_visit: int | None = None
    win_back_status: str | None = None
    contacted_at: datetime | None = None
    can_contact: bool = True
    email_opt_in: bool = False
    in_app_opt_in: bool = False


class CampaignIn(BaseModel):
    offer_text: str | None = None
    cooldown_days: int = Field(default=30, ge=0, le=365)
    limit: int = Field(default=200, ge=1, le=500)


class CampaignResult(BaseModel):
    targeted: int
    sent: int


class WinBackSummaryOut(BaseModel):
    lapsed: int
    contacted: int
    recovered: int
    recovery_rate: float
    recovered_revenue: float
