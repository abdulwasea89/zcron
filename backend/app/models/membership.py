"""OrganizationMember: a user's tenant-scoped role + status within one org.

This is the join between User and Organization. It carries the role (owner /
manager / trainer / front_desk / member), the membership status for members,
and the staff compensation config for trainers (Section 15.1).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Column, JSON, Numeric

from sqlmodel import Field, UniqueConstraint

from app.core.constants import MemberStatus, Role
from app.models.base import TimestampModel, UUIDModel


class OrganizationMember(UUIDModel, TimestampModel, table=True):
    __tablename__ = "organization_members"
    __table_args__ = (
        # One membership per user per tenant (Security Rule #1). Guards the
        # check-then-insert race in invite/signup/import paths.
        UniqueConstraint("organization_id", "user_id", name="uq_organization_members_org_user"),
        UniqueConstraint("organization_id", "attendance_card_uid", name="uq_org_member_attendance_card_uid"),
    )

    organization_id: str = Field(index=True, foreign_key="organizations.id")
    user_id: str = Field(index=True, foreign_key="users.id")

    role: Role = Field(default=Role.MEMBER, index=True)
    member_status: MemberStatus = Field(default=MemberStatus.PENDING_PAYMENT, index=True)

    # Office vertical: set when this member is a seat-holder under a Company.
    # A seat-holder is invited (no self-serve signup) and binds to one company;
    # the company drives occupancy/seat-count analytics. Null for gym/academy.
    company_id: str | None = Field(default=None, foreign_key="companies.id", index=True)

    # Member profile (Section 8.7)
    display_name: str | None = None  # org-scoped name, independent of User.full_name
    phone: str | None = None
    # UID read by a staff-operated RFID/NFC keyboard-wedge reader. This is an
    # identifier only; staff authentication and tenant scoping remain required.
    attendance_card_uid: str | None = Field(default=None, index=True)
    photo_url: str | None = None
    emergency_contact: str | None = None
    goals: str | None = None
    health_notes: str | None = None
    id_document_type: str | None = None
    id_document_last4: str | None = None
    profile_complete: bool = False
    family_owner_member_id: str | None = Field(default=None, foreign_key="organization_members.id", index=True)
    tags: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))

    # Stripe Connect member billing credentials are scoped to this gym's account.
    # Store Stripe references only; never card or bank details.
    stripe_customer_id: str | None = Field(default=None, index=True)
    stripe_default_payment_method_id: str | None = None
    stripe_default_payment_method_type: str | None = None
    recurring_consent_at: datetime | None = None
    stripe_recurring_setup_intent_id: str | None = None

    # Separate member marketing permissions; service and billing messages use
    # their own legal basis and are not controlled by these flags.
    marketing_email_consent: bool = False
    marketing_email_consent_at: datetime | None = None
    marketing_sms_consent: bool = False
    marketing_sms_consent_at: datetime | None = None
    marketing_in_app_consent: bool = False
    marketing_in_app_consent_at: datetime | None = None
    daily_brief_email: bool = False
    dashboard_hidden_attention: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))

    # Lifecycle
    joined_at: datetime | None = None
    banned: bool = False
    status_before_freeze: MemberStatus | None = None

    # ---- Staff compensation (trainer/front desk), Section 15.1 ----
    fixed_monthly_salary: Decimal = Field(default=Decimal("0.00"), sa_column=Column(Numeric(14, 2), nullable=False))
    hourly_rate: Decimal = Field(default=Decimal("0.00"), sa_column=Column(Numeric(14, 2), nullable=False))
    per_class_rate: Decimal = Field(default=Decimal("0.00"), sa_column=Column(Numeric(14, 2), nullable=False))
    commission_rate: Decimal = Field(default=Decimal("0.000000"), sa_column=Column(Numeric(8, 6), nullable=False))  # fraction, e.g. 0.05
    commission_window_months: int = 12  # strict 12-month window (Section 18.1)

    # Trainer who referred/acquired this member (for commission attribution)
    referred_by_member_id: str | None = Field(default=None, foreign_key="organization_members.id")
