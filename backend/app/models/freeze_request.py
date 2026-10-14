"""Member initiated membership pause requests (Blueprint feature 13)."""

from __future__ import annotations

from datetime import datetime

from sqlmodel import Field

from app.models.base import TimestampModel, UUIDModel


class MembershipFreezeRequest(UUIDModel, TimestampModel, table=True):
    __tablename__ = "membership_freeze_requests"

    organization_id: str = Field(index=True, foreign_key="organizations.id")
    member_id: str = Field(index=True, foreign_key="organization_members.id")
    reason: str = Field(max_length=500)
    requested_until: datetime | None = None
    source: str = Field(default="member", index=True)  # member | inbox
    status: str = Field(default="pending", index=True)  # pending | approved | rejected | cancelled
    reviewed_by: str | None = Field(default=None, foreign_key="users.id")
    reviewed_at: datetime | None = None
    decision_note: str | None = Field(default=None, max_length=500)
