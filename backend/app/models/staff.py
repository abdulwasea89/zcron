"""Staff operational models: shift check-ins and simple tasks (Section 15.2, 16.2)."""

from __future__ import annotations

from datetime import datetime

from sqlmodel import Field
from sqlalchemy import Index, text

from app.core.constants import ShiftStatus
from app.models.base import TimestampModel, UUIDModel, utcnow


class Shift(UUIDModel, TimestampModel, table=True):
    """Trainer / front-desk check-in -> check-out. Source of payroll hours."""

    __tablename__ = "shifts"

    organization_id: str = Field(index=True, foreign_key="organizations.id")
    staff_member_id: str = Field(index=True, foreign_key="organization_members.id")
    checked_in_at: datetime = Field(default_factory=utcnow)
    checked_out_at: datetime | None = None
    status: ShiftStatus = Field(default=ShiftStatus.CHECKED_IN, index=True)
    hours: float = 0.0
    is_weekend: bool = False
    is_overtime: bool = False


class ScheduledShift(UUIDModel, TimestampModel, table=True):
    """A planned staff shift; actual hours remain recorded in Shift."""

    __tablename__ = "scheduled_shifts"

    organization_id: str = Field(index=True, foreign_key="organizations.id")
    staff_member_id: str = Field(index=True, foreign_key="organization_members.id")
    starts_at: datetime = Field(index=True)
    ends_at: datetime
    note: str | None = None
    assigned_by: str | None = Field(default=None, foreign_key="users.id")


class Task(UUIDModel, TimestampModel, table=True):
    """Simple task: title + assignee + deadline (Section 16.2)."""

    __tablename__ = "tasks"
    __table_args__ = (Index(
        "uq_tasks_open_retention", "organization_id", "related_member_id", unique=True,
        sqlite_where=text("category = 'retention' AND done = 0"),
        postgresql_where=text("category = 'retention' AND NOT done"),
    ),)

    organization_id: str = Field(index=True, foreign_key="organizations.id")
    title: str
    description: str | None = None
    assignee_member_id: str | None = Field(default=None, foreign_key="organization_members.id")
    created_by: str | None = Field(default=None, foreign_key="users.id")
    deadline: datetime | None = None
    done: bool = False
    category: str = "general"
    related_member_id: str | None = Field(default=None, foreign_key="organization_members.id", index=True)
    case_outcome: str | None = None


class StaffInvite(UUIDModel, TimestampModel, table=True):
    """Single-use invite code for staff/trainers (Section 17.1: trainer codes)."""

    __tablename__ = "staff_invites"

    organization_id: str = Field(index=True, foreign_key="organizations.id")
    code: str = Field(index=True, unique=True)
    role: str = "trainer"
    email: str | None = None
    used: bool = False
    used_by: str | None = Field(default=None, foreign_key="users.id")
    expires_at: datetime | None = None
