"""OrganizationMember: a user's tenant-scoped role + status within one org.

This is the join between User and Organization. It carries the role (owner /
manager / trainer / front_desk / member), the membership status for members,
and the staff compensation config for trainers (Section 15.1).
"""

from __future__ import annotations

from datetime import datetime

from sqlmodel import Field, UniqueConstraint

from app.core.constants import MemberStatus, Role
from app.models.base import TimestampModel, UUIDModel


class OrganizationMember(UUIDModel, TimestampModel, table=True):
    __tablename__ = "organization_members"
    __table_args__ = (
        # One membership per user per tenant (Security Rule #1). Guards the
        # check-then-insert race in invite/signup/import paths.
        UniqueConstraint("organization_id", "user_id", name="uq_organization_members_org_user"),
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
    photo_url: str | None = None
    emergency_contact: str | None = None
    goals: str | None = None
    health_notes: str | None = None
    id_document_type: str | None = None
    id_document_last4: str | None = None
    profile_complete: bool = False

    # Lifecycle
    joined_at: datetime | None = None
    banned: bool = False

    # ---- Staff compensation (trainer/front desk), Section 15.1 ----
    fixed_monthly_salary: float = 0.0
    hourly_rate: float = 0.0
    per_class_rate: float = 0.0
    commission_rate: float = 0.0  # fraction, e.g. 0.05
    commission_window_months: int = 12  # strict 12-month window (Section 18.1)

    # Trainer who referred/acquired this member (for commission attribution)
    referred_by_member_id: str | None = Field(default=None, foreign_key="organization_members.id")
