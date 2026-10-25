"""Trainer-owned workout/session notes for assigned gym clients."""

from __future__ import annotations

from datetime import datetime

from sqlmodel import Field

from app.models.base import TimestampModel, UUIDModel


class TrainerSessionLog(UUIDModel, TimestampModel, table=True):
    __tablename__ = "trainer_session_logs"

    organization_id: str = Field(index=True, foreign_key="organizations.id")
    trainer_member_id: str = Field(index=True, foreign_key="organization_members.id")
    client_member_id: str = Field(index=True, foreign_key="organization_members.id")
    package_id: str | None = Field(default=None, index=True, foreign_key="trainer_packages.id")
    performed_at: datetime = Field(index=True)
    duration_minutes: int
    focus: str
    notes: str = ""
