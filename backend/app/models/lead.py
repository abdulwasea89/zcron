"""Prospects and qualification details for the sales pipeline."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, JSON
from sqlmodel import Field

from app.models.base import TimestampModel, UUIDModel


class Lead(UUIDModel, TimestampModel, table=True):
    __tablename__ = "leads"

    organization_id: str = Field(index=True, foreign_key="organizations.id")
    name: str
    email: str | None = Field(default=None, index=True)
    phone: str | None = None
    goal: str | None = None
    budget: str | None = None
    preferred_times: str | None = None
    preferences: str | None = None
    source: str = Field(default="staff_entered", index=True)
    stage: str = Field(default="new", index=True)
    created_by: str | None = Field(default=None, foreign_key="users.id")
    converted_member_id: str | None = Field(default=None, foreign_key="organization_members.id")
    referred_by_member_id: str | None = Field(default=None, foreign_key="organization_members.id")
    profile_sources: dict[str, str] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))


class LeadBooking(UUIDModel, TimestampModel, table=True):
    __tablename__ = "lead_bookings"

    organization_id: str = Field(index=True, foreign_key="organizations.id")
    lead_id: str = Field(index=True, foreign_key="leads.id")
    booking_type: str = Field(index=True)
    class_session_id: str | None = Field(default=None, index=True, foreign_key="class_sessions.id")
    trainer_member_id: str | None = Field(default=None, foreign_key="organization_members.id")
    starts_at: datetime = Field(index=True)
    ends_at: datetime | None = None
    status: str = Field(default="scheduled", index=True)
    notes: str | None = None
    created_by: str = Field(foreign_key="users.id")
    attended_at: datetime | None = None
    cancelled_at: datetime | None = None
