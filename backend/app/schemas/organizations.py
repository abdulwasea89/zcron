"""Organization schemas (Sections 3, 4, 7)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator
from datetime import date
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.constants import EnrollmentMode, Gender, GymStatus, SaasTier
from app.core.industry import normalize_industry
from app.schemas.auth import NAME_RE


class GymDetails(BaseModel):
    """Step 2 — venue details (Section 4.4, multi-industry Phase 0)."""

    name: str
    country: str = "US"
    timezone: str = "UTC"
    default_currency: str = "USD"
    address: str | None = None
    logo_url: str | None = None
    accent_color: str | None = None
    working_hours: str | None = None
    # Venue vertical: gym | office | academy (canonical key, default gym).
    industry: str = "gym"

    @field_validator("industry")
    @classmethod
    def _normalize_industry(cls, v: str) -> str:
        try:
            return normalize_industry(v).value
        except ValueError as exc:
            raise ValueError("Unknown industry. Choose gym, office or academy.") from exc

    @field_validator("timezone")
    @classmethod
    def _valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("Choose a valid timezone.") from exc
        return value

    @field_validator("default_currency")
    @classmethod
    def _valid_currency(cls, value: str) -> str:
        value = value.strip().upper()
        if not re.fullmatch(r"[A-Z]{3}", value):
            raise ValueError("Currency must be a 3-letter code.")
        return value


class RegisterGymRequest(BaseModel):
    """Complete owner registration: gym details + tier + (stub) card token.

    The owner must already exist and be email-verified (from /auth/register +
    /auth/verify-email). Identified by email here; in production the in-progress
    registration would be tied to a short-lived token.
    """

    owner_email: EmailStr
    details: GymDetails
    tier: SaasTier
    payment_token: str = "tok_stub"  # Stripe-hosted card token in production


class OwnerOnboardingRequest(BaseModel):
    """Profile, workspace and SaaS plan collected after email verification."""
    full_name: str = Field(min_length=2, max_length=100)
    phone: str | None = Field(default=None, max_length=20)
    cnic: str | None = Field(default=None, max_length=15)
    occupation: str | None = Field(default=None, max_length=100)
    education: str | None = Field(default=None, max_length=100)
    address: str | None = Field(default=None, max_length=200)
    city: str | None = Field(default=None, max_length=85)
    date_of_birth: date | None = None
    gender: Gender | None = None
    emergency_contact: str | None = Field(default=None, max_length=120)
    details: GymDetails
    tier: SaasTier

    @field_validator("full_name")
    @classmethod
    def _valid_full_name(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 2 or not NAME_RE.match(value):
            raise ValueError("Enter a valid full name.")
        return value

    @field_validator("phone")
    @classmethod
    def _valid_onboarding_phone(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        cleaned = re.sub(r"[\s\-()]", "", value.strip())
        if not re.fullmatch(r"\+?[0-9]{7,15}", cleaned):
            raise ValueError("Enter a valid phone number.")
        return cleaned


class CheckoutSessionOut(BaseModel):
    checkout_url: str
    session_id: str


class CheckoutConfirmIn(BaseModel):
    session_id: str = Field(min_length=8, max_length=255)


class OrganizationOut(BaseModel):
    id: str
    name: str
    org_code: str
    saas_tier: str
    saas_status: str
    enrollment_mode: str
    gym_status: str
    member_cap: int | None
    stripe_connect_status: str
    accent_color: str | None = None
    logo_url: str | None = None
    mfa_required: bool = False
    industry: str = "gym"
    default_currency: str = "USD"
    country: str = "US"
    timezone: str = "UTC"
    created_at: datetime
    onboarding_complete: bool = True


class RegisterGymResponse(BaseModel):
    organization: OrganizationOut
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class SetupChecklist(BaseModel):
    gym_registered: bool = True
    saas_active: bool
    stripe_connected: bool
    plan_published: bool
    enrollment_configured: bool
    staff_invited: bool
    office_configured: bool
    member_signup_unblocked: bool
    # Industry-ordered onboarding steps: [{code, label, done}, ...]
    steps: list[dict] = []


class EnrollmentModeUpdate(BaseModel):
    enrollment_mode: EnrollmentMode


class GymStatusUpdate(BaseModel):
    gym_status: GymStatus


class ConnectOnboardingOut(BaseModel):
    account_id: str
    onboarding_url: str


class OrgCodeRotateOut(BaseModel):
    org_code: str


class OrgNameUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=80)

    @field_validator("name")
    @classmethod
    def _strip_name(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 2:
            raise ValueError("Gym name is too short")
        if not NAME_RE.match(v):
            raise ValueError("Gym name may only contain letters, spaces, . ' and -")
        return v


class BulkImportResult(BaseModel):
    created: int
    updated: int = 0
    skipped: int
    errors: list[dict]


class CreateOrganizationRequest(BaseModel):
    """Existing authenticated user creates another gym."""

    details: GymDetails
    tier: SaasTier
    payment_token: str = "tok_stub"


class SwitchOrgRequest(BaseModel):
    """Switch to a different organization the user belongs to."""

    organization_id: str


class InvoiceSettings(BaseModel):
    """B2B invoice template (office vertical): what appears on an issued invoice.

    Flipping any field on marks the 'invoices' setup-checklist step done."""

    legal_name: str | None = None
    address: str | None = None
    tax_id: str | None = None
    payment_terms_days: int | None = Field(default=None, ge=0, le=120)
