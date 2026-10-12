"""Attendance: one member gym visit — the behaviour signal (Section 1.3, #18).

Every front-desk check-in, QR scan, self-check-in or class attendance becomes an
append-only row here. This is the "what members do" stream the retention model
needs: the blueprint calls non-attendance the strongest churn predictor, and
without it churn scoring has nothing to reason over.

Rows are tenant-scoped (``organization_id``) so the isolation filter is a plain
column predicate (Security Rule #1). They are point events — a member may check
in more than once a day — and carry ``idempotency_key`` so a double-tap cannot
create two visits.
"""

from __future__ import annotations

from datetime import datetime

from sqlmodel import Field

from app.core.constants import AttendanceMethod, AttendanceSource
from app.models.base import TimestampModel, UUIDModel, utcnow


class Attendance(UUIDModel, TimestampModel, table=True):
    __tablename__ = "attendance"

    organization_id: str = Field(index=True, foreign_key="organizations.id")
    member_id: str = Field(index=True, foreign_key="organization_members.id")

    checked_in_at: datetime = Field(default_factory=utcnow, index=True)

    method: AttendanceMethod = Field(default=AttendanceMethod.MANUAL, index=True)
    source: AttendanceSource = Field(default=AttendanceSource.FRONT_DESK, index=True)

    # Staff actor who logged the visit; null for self-check-in / integrations.
    checked_in_by: str | None = Field(default=None, foreign_key="users.id")

    # Set when the visit came from a class booking (Section 1.8).
    class_session_id: str | None = Field(default=None, foreign_key="class_sessions.id")

    note: str | None = None
    idempotency_key: str | None = Field(default=None, index=True)
    credit_subscription_id: str | None = Field(default=None, foreign_key="subscriptions.id")
