"""Auth request/response schemas (Sections 4, 5, 8, 9)."""

from __future__ import annotations

import re

from pydantic import BaseModel, EmailStr, Field, model_validator

from app.schemas.common import TokenPair
from app.schemas.members import MemberProfileUpdate

# --- Shared validation patterns (mirrored on the frontend) ---------------
# Person/place names: letters (incl. accented Latin), spaces, . ' - — no digits.
NAME_RE = re.compile(r"^[A-Za-zÀ-ɏ][A-Za-zÀ-ɏ .'\-]*$")
# CNIC: 13 digits, optionally grouped 5-7-1 with dashes (e.g. 42101-1234567-8).
CNIC_RE = re.compile(r"^\d{5}-?\d{7}-?\d$")
# Phone: optional leading +, then 7–15 digits once separators are stripped.
PHONE_RE = re.compile(r"^\+?[0-9]{7,15}$")

MIN_OWNER_AGE = 16
MAX_OWNER_AGE = 120


class OwnerRegisterStart(BaseModel):
    """Create login credentials first; profile details are collected in setup."""

    email: EmailStr
    password: str
    confirm_password: str

    @model_validator(mode="after")
    def _passwords_match(self) -> "OwnerRegisterStart":
        if self.password != self.confirm_password:
            raise ValueError("Passwords do not match")
        return self


class EmailVerifyRequest(BaseModel):
    email: EmailStr
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class ResendCodeRequest(BaseModel):
    email: EmailStr


class LoginRequest(BaseModel):
    """Web/mobile login. org_code optional for owners, required for members."""

    email: EmailStr
    password: str
    org_code: str | None = None
    organization_id: str | None = None
    remember: bool = False
    mfa_code: str | None = None


class MemberLoginRequest(BaseModel):
    """Returning member login validates all three together (Section 9.1)."""

    org_code: str
    email: EmailStr
    password: str
    remember: bool = False
    mfa_code: str | None = None


class MagicLinkRequest(BaseModel):
    """Mobile login Method B — org code + email (Section 5.4).

    The email must belong to an admin of the named org; a single-use link is
    then emailed. Response is deliberately vague (never leaks membership).
    """

    org_code: str
    email: EmailStr


class MagicLinkVerify(BaseModel):
    """Consume the emailed magic-link token and issue a session (Section 5.4)."""

    org_code: str
    email: EmailStr
    token: str
    remember: bool = False
    mfa_code: str | None = None


class MfaConfirm(BaseModel):
    code: str = Field(min_length=6, max_length=6)


class MfaDisable(BaseModel):
    password: str


class MfaEnrollResponse(BaseModel):
    secret: str
    otpauth_uri: str
    current_code: str


class MfaStatus(BaseModel):
    mfa_enabled: bool


class RefreshRequest(BaseModel):
    refresh_token: str
    organization_id: str | None = None


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    email: EmailStr
    token: str
    new_password: str


class LoginUserOut(BaseModel):
    """Authenticated user identity embedded in every token-bearing response."""

    user_id: str
    email: str
    role: str
    org_id: str
    member_id: str | None = None
    member_status: str | None = None


class LoginResponse(TokenPair):
    member_status: str | None = None
    requires_mfa: bool = False
    organizations: list[dict] | None = None
    user: LoginUserOut | None = None


class SwitchOrgRequest(BaseModel):
    """Switch to a different organization the user belongs to."""

    organization_id: str


class RecoverCodesRequest(BaseModel):
    """Request an email listing all gyms and their org codes."""

    email: EmailStr


class SessionInfo(BaseModel):
    id: str
    device_type: str | None = None
    os: str | None = None
    ip_address: str | None = None
    last_activity_at: str | None = None
    revoked: bool = False
    current: bool = False


class AdminSessionInfo(BaseModel):
    """Session info with user details, for owner/manager session management."""

    id: str
    user_id: str
    user_email: str
    user_name: str | None = None
    device_type: str | None = None
    os: str | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    last_activity_at: str | None = None
    revoked: bool = False
    current: bool = False


class ProfileOut(BaseModel):
    full_name: str | None = None
    email: str
    phone: str | None = None
    address: str | None = None
    city: str | None = None
    occupation: str | None = None
    education: str | None = None
    emergency_contact: str | None = None
    date_of_birth: str | None = None
    gender: str | None = None
    photo_url: str | None = None
    goals: str | None = None
    health_notes: str | None = None
    id_document_type: str | None = None
    id_document_last4: str | None = None
    summary: str | None = None


class ProfileUpdate(MemberProfileUpdate):
    full_name: str | None = None
    address: str | None = None
    city: str | None = None
    occupation: str | None = None
    education: str | None = None
