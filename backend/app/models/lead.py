"""Prospects and qualification details for the sales pipeline."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, Column, Index, JSON, UniqueConstraint
from sqlmodel import Field

from app.models.base import TimestampModel, UUIDModel


class Lead(UUIDModel, TimestampModel, table=True):
    __tablename__ = "leads"
    __table_args__ = (
        CheckConstraint(
            "lost_reason IS NULL OR lost_reason IN "
            "('price', 'schedule', 'timing', 'location', 'joined_elsewhere', 'no_response', 'not_interested', 'other')",
            name="ck_leads_lost_reason",
        ),
        Index("ix_leads_org_source_contact_handle", "organization_id", "source", "contact_handle"),
    )

    organization_id: str = Field(index=True, foreign_key="organizations.id")
    name: str
    email: str | None = Field(default=None, index=True)
    phone: str | None = None
    contact_handle: str | None = None
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
    email_followup_consent: bool = Field(default=False, nullable=False)
    email_followup_consent_at: datetime | None = None
    sms_followup_consent: bool = Field(default=False, nullable=False)
    sms_followup_consent_at: datetime | None = None
    lost_reason: str | None = Field(default=None, index=True)


class LeadBooking(UUIDModel, TimestampModel, table=True):
    __tablename__ = "lead_bookings"
    __table_args__ = (
        CheckConstraint("booking_type IN ('trial', 'tour')", name="ck_lead_booking_type"),
        CheckConstraint(
            "(booking_type = 'trial' AND class_session_id IS NOT NULL) OR "
            "(booking_type = 'tour' AND class_session_id IS NULL)",
            name="ck_lead_booking_target",
        ),
        CheckConstraint("ends_at IS NULL OR ends_at > starts_at", name="ck_lead_booking_time_range"),
        CheckConstraint(
            "status IN ('scheduled', 'attended', 'no_show', 'cancelled')",
            name="ck_lead_booking_status",
        ),
    )

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


class LeadFollowUp(UUIDModel, TimestampModel, table=True):
    __tablename__ = "lead_followups"
    __table_args__ = (
        UniqueConstraint("lead_id", "day", name="uq_lead_followup_day"),
        CheckConstraint("day IN (0, 1, 3, 7)", name="ck_lead_followup_day"),
        CheckConstraint(
            "status IN ('scheduled', 'due', 'completed', 'skipped')",
            name="ck_lead_followup_status",
        ),
        CheckConstraint(
            "email_status IN ('pending', 'sent', 'failed', 'skipped')",
            name="ck_lead_followup_email_status",
        ),
    )

    organization_id: str = Field(index=True, foreign_key="organizations.id")
    lead_id: str = Field(index=True, foreign_key="leads.id")
    day: int = Field(index=True)
    due_at: datetime = Field(index=True)
    status: str = Field(default="scheduled", index=True)
    completed_at: datetime | None = None
    completed_by: str | None = Field(default=None, foreign_key="users.id")
    note: str | None = None
    email_status: str = Field(default="pending", index=True)
    email_attempted_at: datetime | None = None
    email_sent_at: datetime | None = None
    email_attempts: int = Field(default=0, nullable=False)
