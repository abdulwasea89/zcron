"""Class session & booking schemas (Sections 8, 9, 15).

Members book published class sessions; a trainer check-in gates per-class
payroll. Bookings are idempotent (Security Rule #2).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class ClassSessionCreate(BaseModel):
    title: str
    trainer_member_id: str | None = None
    starts_at: datetime
    ends_at: datetime | None = None
    capacity: int = 20


class ClassSessionOut(BaseModel):
    id: str
    title: str
    trainer_member_id: str | None
    starts_at: datetime
    ends_at: datetime | None
    capacity: int
    booked_count: int
    trainer_checked_in: bool
    cancelled: bool


class BookingCreate(BaseModel):
    class_session_id: str


class WaitlistCreate(BaseModel):
    member_id: str


class BookingOut(BaseModel):
    id: str
    class_session_id: str
    member_id: str
    status: str


class BookingWithMember(BaseModel):
    booking_id: str
    class_session_id: str
    member_id: str
    member_name: str | None
    member_email: str
    status: str


class MyBookingOut(BaseModel):
    """A member's booking joined with its session (self-service, member role)."""

    booking_id: str
    status: str
    class_session: ClassSessionOut
