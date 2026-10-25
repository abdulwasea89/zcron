"""Class sessions and member bookings (Sections 8, 9, 15).

A ClassSession is a scheduled class taught by a trainer. Bookings link members to
sessions and feed both attendance (member side) and per-class payroll (trainer
side, only when the trainer actually checked in).
"""

from __future__ import annotations

from datetime import datetime

from sqlmodel import Field

from app.core.constants import BookingStatus
from app.models.base import TimestampModel, UUIDModel


class ClassSession(UUIDModel, TimestampModel, table=True):
    __tablename__ = "class_sessions"

    organization_id: str = Field(index=True, foreign_key="organizations.id")
    # Slot category (Phase 0): class | space_slot | lesson.
    # gym uses 'class'; office desk/room slots use 'space_slot'; academy
    # per-batch lessons use 'lesson' — all share one scheduling table.
    category: str = "class"
    title: str
    trainer_member_id: str | None = Field(default=None, foreign_key="organization_members.id")
    starts_at: datetime = Field(index=True)
    ends_at: datetime | None = None
    capacity: int = 20
    booked_count: int = 0
    trainer_checked_in: bool = False  # gate for per-class payroll (Section 15.2)
    cancelled: bool = False


class ClassBooking(UUIDModel, TimestampModel, table=True):
    __tablename__ = "class_bookings"

    organization_id: str = Field(index=True, foreign_key="organizations.id")
    class_session_id: str = Field(index=True, foreign_key="class_sessions.id")
    member_id: str = Field(index=True, foreign_key="organization_members.id")
    status: BookingStatus = Field(default=BookingStatus.BOOKED, index=True)
    idempotency_key: str | None = Field(default=None, index=True)
    reminder_created_at: datetime | None = None
    reminder_email_accepted: bool = False
