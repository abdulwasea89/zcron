"""Admin member directory & management schemas (Sections 8, 9, 7.6)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_serializer, field_validator

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
    fixed_monthly_salary: Decimal = Decimal("0.00")
    hourly_rate: Decimal = Decimal("0.00")
    per_class_rate: Decimal = Decimal("0.00")
    commission_rate: Decimal = Decimal("0.000000")
    # Display names of the trainers currently assigned to this member.
    assigned_trainers: list[str] = []

    @field_serializer(
        "fixed_monthly_salary", "hourly_rate", "per_class_rate", "commission_rate", when_used="json"
    )
    def _serialize_compensation(self, value: Decimal) -> float:
        return float(value)


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


class FreezeRequestCreate(BaseModel):
    reason: str = Field(min_length=3, max_length=500)
    requested_until: datetime | None = None

    @field_validator("reason")
    @classmethod
    def clean_reason(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 3:
            raise ValueError("Please explain why you need to pause your membership.")
        return value


class FreezeRequestDecision(BaseModel):
    approve: bool
    note: str | None = Field(default=None, max_length=500)


class FreezeRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    member_id: str
    reason: str
    requested_until: datetime | None
    source: str
    status: str
    created_at: datetime
    reviewed_at: datetime | None
    decision_note: str | None


class FreezeRequestQueueOut(FreezeRequestOut):
    member_name: str
    member_email: str


class MembershipChangeCreate(BaseModel):
    request_type: str
    target_plan_id: str | None = None
    reason: str = Field(min_length=3, max_length=500)

    @field_validator("reason")
    @classmethod
    def clean_change_reason(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 3:
            raise ValueError("Please explain the membership change request.")
        return value


class MembershipChangeDecision(BaseModel):
    approve: bool = False
    offer_pause: bool = False
    offer_type: str | None = None
    offer_plan_id: str | None = None
    offer_discount_percent: float | None = Field(default=None, ge=1, le=100)
    offer_discount_months: int | None = Field(default=None, ge=1, le=12)
    effective_timing: str = "now"  # now | period_end
    note: str | None = Field(default=None, max_length=500)


class MembershipChangeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    member_id: str
    subscription_id: str
    request_type: str
    target_plan_id: str | None
    reason: str
    status: str
    save_offer: str | None
    offer_type: str | None = None
    offer_plan_id: str | None = None
    offer_discount_percent: float | None = None
    amount_due: float = 0.0
    effective_at: datetime | None = None
    created_at: datetime
    reviewed_at: datetime | None
    decision_note: str | None


class MembershipChangePaymentOut(BaseModel):
    payment_required: bool
    payment_id: str | None = None
    payment_intent_id: str | None = None
    client_secret: str | None = None
    amount: float = 0.0
    currency: str = "USD"


class MembershipChangePaymentConfirm(BaseModel):
    payment_intent_id: str


class MembershipChangeQueueOut(MembershipChangeOut):
    member_name: str
    member_email: str
    current_plan_name: str
    target_plan_name: str | None


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
    credits_allowance: int | None = None
    audience: str = "standard"
    family_capacity: int | None = None


class FamilyMemberOut(BaseModel):
    member_id: str
    name: str


class FamilyLinkRequest(BaseModel):
    member_id: str


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
    family_owner: FamilyMemberOut | None = None
    family_members: list[FamilyMemberOut] = []
