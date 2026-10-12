"""Admin member directory & management schemas (Sections 8, 9, 7.6)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.schemas.payments import PaymentOut


class MemberDirectoryItem(BaseModel):
    member_id: str
    user_id: str
    email: str
    full_name: str | None
    display_name: str | None = None
    photo_url: str | None = None
    role: str
    member_status: str
    phone: str | None
    profile_complete: bool
    created_at: datetime
    fixed_monthly_salary: float = 0.0
    hourly_rate: float = 0.0
    per_class_rate: float = 0.0
    commission_rate: float = 0.0
    # Display names of the trainers currently assigned to this member.
    assigned_trainers: list[str] = []


class MemberProfileUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=160)
    phone: str | None = Field(default=None, max_length=40)
    photo_url: str | None = Field(default=None, max_length=2048)
    emergency_contact: str | None = Field(default=None, max_length=120)
    goals: str | None = Field(default=None, max_length=1000)
    health_notes: str | None = Field(default=None, max_length=2000)
    id_document_type: str | None = Field(default=None, max_length=60)
    id_document_last4: str | None = Field(default=None, max_length=4)

    @field_validator("display_name", "phone", "photo_url", "emergency_contact", "goals", "health_notes", "id_document_type", "id_document_last4")
    @classmethod
    def clean_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None

    @field_validator("photo_url")
    @classmethod
    def safe_photo_url(cls, value: str | None) -> str | None:
        if value and not value.startswith("https://"):
            raise ValueError("Photo URL must use HTTPS.")
        return value

    @field_validator("id_document_last4")
    @classmethod
    def safe_id_suffix(cls, value: str | None) -> str | None:
        if value and (len(value) != 4 or not value.isalnum()):
            raise ValueError("Use only the final four letters or digits of the ID.")
        return value.upper() if value else None


class MemberProfileOut(BaseModel):
    display_name: str | None = None
    phone: str | None = None
    photo_url: str | None = None
    emergency_contact: str | None = None
    goals: str | None = None
    health_notes: str | None = None
    id_document_type: str | None = None
    id_document_last4: str | None = None
    summary: str


class TrainerAssign(BaseModel):
    trainer_member_id: str


class TrainerAssignment(BaseModel):
    """One active trainer->member assignment, resolved for API responses."""

    member_id: str
    trainer_member_id: str
    trainer_name: str
    assigned_at: datetime
    active: bool


class ClientAssignment(BaseModel):
    """A member assigned to a trainer, resolved for the 'my clients' view."""

    member_id: str
    member_name: str | None
    member_email: str
    member_status: str
    assigned_at: datetime


class MemberStatusChange(BaseModel):
    """Admin status action: ban / unban / freeze / unfreeze / cancel."""

    action: str
    reason: str | None = None


class RoleChange(BaseModel):
    role: str


class EmailUpdate(BaseModel):
    email: EmailStr


class ApprovalDecision(BaseModel):
    approve: bool
    reason: str | None = None


class MemberInvite(BaseModel):
    email: EmailStr


class MemberInviteOut(BaseModel):
    member_id: str
    email: str
    invite_code: str
    member_status: str
    # True when the email was actually delivered by a provider. False in stub
    # mode (no provider) — the UI then shows `invite_code` for manual sharing.
    email_delivered: bool = False


class MemberSubscriptionOut(BaseModel):
    """A member's current subscription joined with its plan (detail page)."""

    subscription_id: str
    plan_id: str
    plan_name: str
    plan_price: float
    price_snapshot: float
    currency: str
    billing_type: str
    status: str
    started_at: datetime
    current_period_end: datetime | None
    grace_until: datetime | None
    frozen_until: datetime | None
    cancelled_at: datetime | None
    classes_remaining: int | None


class PendingPaymentItem(BaseModel):
    """One thing a member still owes or has a pending/failed payment attempt for."""

    kind: str  # first_payment | renewal | failed_attempt | pending_attempt
    label: str
    amount: float | None = None
    currency: str | None = None
    due_at: datetime | None = None
    payment_id: str | None = None


class MemberDetailOut(BaseModel):
    member: MemberDirectoryItem
    profile: MemberProfileOut
    subscription: MemberSubscriptionOut | None = None
    payments: list[PaymentOut] = []
    pending_payments: list[PendingPaymentItem] = []
    trainer_assignments: list[TrainerAssignment] = []
