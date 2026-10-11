"""API schemas for gym sales leads."""

from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.constants import LeadSource


def _clean_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _clean_phone(value: str | None) -> str | None:
    cleaned = _clean_optional_text(value)
    if cleaned is None:
        return None
    prefix = "+" if cleaned.startswith("+") else ""
    digits = re.sub(r"\D", "", cleaned)
    if len(digits) < 7:
        raise ValueError("Phone number must contain at least 7 digits.")
    return f"{prefix}{digits}"


class LeadProfileFields(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=40)
    goal: str | None = Field(default=None, max_length=2000)
    budget: str | None = Field(default=None, max_length=200)
    preferred_times: str | None = Field(default=None, max_length=500)
    preferences: str | None = Field(default=None, max_length=2000)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str | None) -> str | None:
        cleaned = _clean_optional_text(value)
        if value is not None and cleaned is None:
            raise ValueError("Name cannot be blank.")
        return cleaned

    @field_validator("email")
    @classmethod
    def clean_email(cls, value: str | None) -> str | None:
        cleaned = _clean_optional_text(value)
        return cleaned.lower() if cleaned else None

    @field_validator("phone")
    @classmethod
    def clean_phone(cls, value: str | None) -> str | None:
        return _clean_phone(value)

    @field_validator("goal", "budget", "preferred_times", "preferences")
    @classmethod
    def clean_profile_text(cls, value: str | None) -> str | None:
        return _clean_optional_text(value)


class LeadCreate(LeadProfileFields):
    name: str = Field(min_length=1, max_length=160)
    source: LeadSource = LeadSource.STAFF_ENTERED


class LeadUpdate(LeadProfileFields):
    source: LeadSource | None = None
    stage: str | None = Field(default=None, pattern="^(new|contacted|trial_booked|visited|joined|lost)$")


class LeadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    email: str | None
    phone: str | None
    goal: str | None
    budget: str | None
    preferred_times: str | None
    preferences: str | None
    source: str
    stage: str
    profile_sources: dict[str, str]
    created_at: datetime
    updated_at: datetime


class LeadHistoryItem(BaseModel):
    id: str
    previous_stage: str | None
    stage: str
    actor_name: str | None
    actor_user_id: str | None
    created_at: datetime
    origin: str
    created: bool


class LeadHistoryOut(BaseModel):
    items: list[LeadHistoryItem]
    total: int
    page: int
    page_size: int


def _naive_utc(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


class TrialSlotOut(BaseModel):
    id: str
    title: str
    trainer_member_id: str | None
    starts_at: datetime
    ends_at: datetime | None
    capacity: int
    booked_count: int
    remaining_capacity: int


class LeadBookingCreate(BaseModel):
    booking_type: Literal["trial", "tour"]
    class_session_id: str | None = None
    trainer_member_id: str | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("starts_at", "ends_at")
    @classmethod
    def normalize_timestamp(cls, value: datetime | None) -> datetime | None:
        return _naive_utc(value)

    @field_validator("notes")
    @classmethod
    def clean_notes(cls, value: str | None) -> str | None:
        return _clean_optional_text(value)

    @model_validator(mode="after")
    def validate_booking_target(self):
        if self.booking_type == "trial" and not self.class_session_id:
            raise ValueError("A trial must use an available class slot.")
        if self.booking_type == "tour" and self.starts_at is None:
            raise ValueError("A tour start time is required.")
        if self.booking_type == "tour" and self.class_session_id is not None:
            raise ValueError("A tour cannot use a class slot.")
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            raise ValueError("End time must be after start time.")
        return self


class LeadBookingStatusUpdate(BaseModel):
    status: Literal["attended", "no_show", "cancelled"]


class LeadBookingOut(BaseModel):
    id: str
    lead_id: str
    booking_type: str
    class_session_id: str | None
    class_title: str | None
    trainer_member_id: str | None
    starts_at: datetime
    ends_at: datetime | None
    status: str
    notes: str | None
    attended_at: datetime | None
    cancelled_at: datetime | None
    created_at: datetime
    updated_at: datetime
