"""Member signup & membership schemas (Sections 8, 9)."""

from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field, field_validator


class SignupStart(BaseModel):
    """Step 1 — org code entry (Section 8.2)."""

    org_code: str
    captcha_token: str | None = None
    referral_code: str | None = Field(default=None, max_length=32)


class SignupStartOut(BaseModel):
    organization_id: str
    organization_name: str
    enrollment_mode: str
    accepting_signups: bool


class SignupEmail(BaseModel):
    """Step 3 — email + verification request."""

    org_code: str
    email: EmailStr
    captcha_token: str | None = None


class SignupVerify(BaseModel):
    org_code: str
    email: EmailStr
    code: str


class SignupSetPassword(BaseModel):
    """Step 4 — password. Creates account in pending_payment."""

    org_code: str
    email: EmailStr
    password: str
    referral_code: str | None = Field(default=None, max_length=32)


class SignupSetPasswordOut(BaseModel):
    member_id: str
    organization_id: str
    member_status: str


class RedeemInvite(BaseModel):
    """Invited member claims their invite: code + a new password (Section 8.4)."""

    org_code: str
    email: EmailStr
    # Invite codes are 43-char tokens, long enough that mail clients soft-wrap them.
    # Copying from an email therefore tends to carry a newline or a space into the
    # field, which would otherwise hash to a different value and read as a wrong
    # code. Normalize before hashing.
    code: str = Field(min_length=1, max_length=256)

    @field_validator("code")
    @classmethod
    def _strip_code(cls, v: str) -> str:
        cleaned = "".join(v.split())
        if not cleaned:
            raise ValueError("Invite code is required.")
        return cleaned

    password: str


class PublicPlanOut(BaseModel):
    id: str
    name: str
    public_description: str | None
    price: float
    currency: str
    billing_type: str
    featured: bool
    audience: str = "standard"
    family_capacity: int | None = None
    cycle_length: int | None = None
    cycle_unit: str | None = None
    pack_size: int | None = None
    validity_days: int | None = None
    included_credits: int | None = None
    off_peak_start: str | None = None
    off_peak_end: str | None = None


class SignupPay(BaseModel):
    """Step 6 — idempotent payment for chosen plan."""

    org_code: str
    email: EmailStr
    plan_id: str
    payment_token: str = "tok_stub"


class ProfileComplete(BaseModel):
    """Step 7 — profile setup."""

    full_name: str
    photo_url: str | None = None
    phone: str | None = None
    emergency_contact: str | None = None


class MemberOut(BaseModel):
    member_id: str
    user_id: str
    email: str
    full_name: str | None
    role: str
    member_status: str
    profile_complete: bool
