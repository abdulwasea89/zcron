"""Retention schemas: attendance-drop + churn-risk roster (#33, #34)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class RetentionCaseUpdate(BaseModel):
    next_action: str = Field(min_length=1, max_length=1000)
    assignee_member_id: str | None = None
    due_at: datetime | None = None
    outcome: Literal["payment_received", "returned", "plan_changed", "paused", "declined", "unreachable", "completed", "cancelled"] | None = None

    @field_validator("next_action")
    @classmethod
    def trim_action(cls, value):
        if not value.strip():
            raise ValueError("Describe the next action.")
        return value.strip()

    @field_validator("due_at")
    @classmethod
    def utc_due(cls, value):
        return value.astimezone(timezone.utc).replace(tzinfo=None) if value and value.tzinfo else value


class AttendanceTrendOut(BaseModel):
    eligible: bool
    baseline_weekly: float
    recent_weekly: float
    drop_ratio: float | None = None
    is_drop: bool
    severity: str | None = None        # silent | severe | moderate | null
    recent_visits: int
    baseline_visits: int
    days_since_last_visit: int | None = None


class RiskReasonOut(BaseModel):
    code: str
    label: str
    weight: int


class MemberRiskOut(BaseModel):
    member_id: str
    name: str | None = None
    phone: str | None = None
    status: str
    score: int
    band: str                          # high | medium | low
    trend: AttendanceTrendOut
    reasons: list[RiskReasonOut]
    days_since_last_visit: int | None = None
    recent_weekly: float = 0.0
    baseline_weekly: float = 0.0


class RetentionSummaryOut(BaseModel):
    scored: int
    high: int
    medium: int
    low: int
    attendance_drops: int
    silent: int
    revenue_at_risk: float
    revenue_at_risk_by_currency: dict[str, float] = Field(default_factory=dict)


class RetentionWinOut(BaseModel):
    id: str
    kind: str  # lead_converted | renewal_recovered
    payment_id: str | None = None
    lead_id: str | None = None
    member_id: str | None
    member_name: str
    amount: float | None = None
    currency: str | None = None
    recovered_at: datetime
    lead_source: str | None = None
