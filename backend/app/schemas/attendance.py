"""Attendance schemas (Section 1.3, #18).

A check-in returns the visit row plus the "status on check-in" flags the front
desk needs: membership state, dues, birthday, and how long since the member was
last seen (the at-risk hint). Listing and summary shapes power the console.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class CheckInCreate(BaseModel):
    """Front-desk / QR check-in for a member (staff-initiated)."""

    member_id: str
    method: str = "manual"      # AttendanceMethod value
    note: str | None = None


class AttendanceCardCheckIn(BaseModel):
    """UID captured from a staff-operated card/RFID reader."""

    card_uid: str = Field(min_length=3, max_length=128)


class AttendanceCardAssign(BaseModel):
    """Link a physical card to one member within the current organization."""

    card_uid: str = Field(min_length=3, max_length=128)


class CheckInOut(BaseModel):
    """The created (or replayed) visit plus status-on-check-in flags."""

    id: str
    member_id: str
    member_name: str | None
    checked_in_at: datetime
    method: str
    source: str
    class_session_id: str | None = None
    note: str | None = None

    # ---- status on check-in ----
    membership_status: str
    payment_due: bool
    amount_due: float | None = None
    currency: str | None = None
    birthday_today: bool
    days_since_last_visit: int | None
    at_risk: bool
    visits_today: int
    hint: str | None = None
    credit_consumed: bool = False
    access_warning: str | None = None


class AttendanceOut(BaseModel):
    """A single visit as shown in lists and member history.

    Today's feed carries the durable status flags (dues, birthday) and the
    front-desk hint; the per-member history leaves them unset.
    """

    id: str
    member_id: str
    member_name: str | None
    checked_in_at: datetime
    method: str
    source: str
    class_session_id: str | None = None
    note: str | None = None

    membership_status: str | None = None
    payment_due: bool = False
    amount_due: float | None = None
    currency: str | None = None
    birthday_today: bool = False
    at_risk: bool = False
    days_since_last_visit: int | None = None
    hint: str | None = None
    credit_consumed: bool = False


class AttendanceSummary(BaseModel):
    """Front-desk console headline numbers for today."""

    today_count: int
    unique_today: int
    avg_last_7_days: float
    dormant_members: int = Field(
        description="Active members with no visit in the last 14 days."
    )


class AttendanceMember(BaseModel):
    """A member search hit for the check-in box, with its status card."""

    member_id: str
    member_name: str | None
    member_email: str
    member_status: str
    phone: str | None = None
    has_attendance_card: bool = False

    payment_due: bool = False
    amount_due: float | None = None
    currency: str | None = None
    birthday_today: bool = False
    at_risk: bool = False
    days_since_last_visit: int | None = None
    hint: str | None = None


class SyncCheckIn(BaseModel):
    """One offline-queued check-in being flushed to the server (#23)."""

    id: str                      # client-side id, echoed back
    member_id: str
    method: str = "manual"
    checked_in_at: datetime | None = None
    idempotency_key: str


class SyncIn(BaseModel):
    items: list[SyncCheckIn]


class SyncResult(BaseModel):
    id: str
    status: str                  # "synced" | "error"
    attendance_id: str | None = None
    detail: str | None = None


class SyncOut(BaseModel):
    results: list[SyncResult]

