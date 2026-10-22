"""Staff schemas: invites, shifts, tasks (Sections 15.2, 16.2, 17.1)."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.constants import Role


class StaffInviteCreate(BaseModel):
    role: Role = Role.TRAINER
    email: str | None = None


class StaffInviteOut(BaseModel):
    id: str
    code: str
    role: str
    email: str | None
    used: bool


class InviteEmailUpdate(BaseModel):
    email: str


class InviteRoleUpdate(BaseModel):
    role: str


class StaffInviteRedeem(BaseModel):
    # Codes are long tokens that mail clients soft-wrap; see RedeemInvite.
    code: str = Field(min_length=1, max_length=256)
    full_name: str
    password: str

    @field_validator("code")
    @classmethod
    def _strip_code(cls, v: str) -> str:
        cleaned = "".join(v.split())
        if not cleaned:
            raise ValueError("Invite code is required.")
        return cleaned


class ShiftOut(BaseModel):
    id: str
    staff_member_id: str
    checked_in_at: datetime
    checked_out_at: datetime | None
    status: str
    hours: float


class ShiftScheduleCreate(BaseModel):
    staff_member_id: str
    starts_at: datetime
    ends_at: datetime
    note: str | None = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def validate_times(self):
        starts = self.starts_at.astimezone(timezone.utc) if self.starts_at.tzinfo else self.starts_at.replace(tzinfo=timezone.utc)
        ends = self.ends_at.astimezone(timezone.utc) if self.ends_at.tzinfo else self.ends_at.replace(tzinfo=timezone.utc)
        if ends <= starts:
            raise ValueError("Shift end must be after its start.")
        return self


class ShiftScheduleOut(BaseModel):
    id: str
    staff_member_id: str
    starts_at: datetime
    ends_at: datetime
    note: str | None


class CompensationUpdate(BaseModel):
    fixed_monthly_salary: Decimal | None = Field(default=None, max_digits=14, decimal_places=2, ge=0)
    hourly_rate: Decimal | None = Field(default=None, max_digits=14, decimal_places=2, ge=0)
    per_class_rate: Decimal | None = Field(default=None, max_digits=14, decimal_places=2, ge=0)
    commission_rate: Decimal | None = Field(default=None, max_digits=8, decimal_places=6, ge=0, le=1)


class TaskCreateIn(BaseModel):
    title: str
    description: str | None = None
    assignee_member_id: str | None = None
    deadline: datetime | None = None


class TaskUpdateIn(BaseModel):
    title: str | None = None
    description: str | None = None
    assignee_member_id: str | None = None
    deadline: datetime | None = None


class TaskOut(BaseModel):
    id: str
    title: str
    description: str | None
    assignee_member_id: str | None
    deadline: datetime | None
    done: bool
