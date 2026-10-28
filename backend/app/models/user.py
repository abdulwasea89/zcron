"""User: cross-tenant identity (Section: Database Core Schema).

One user (one email) can belong to multiple organizations via
OrganizationMember rows. Password and MFA config live here; role/status live on
the membership.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlmodel import Field

from app.core.constants import Gender
from app.models.base import TimestampModel, UUIDModel


class User(UUIDModel, TimestampModel, table=True):
    __tablename__ = "users"

    email: str = Field(index=True, unique=True)
    full_name: str | None = None
    hashed_password: str
    email_verified: bool = False

    # Owner profile captured at registration (Section 4.2).
    cnic: str | None = Field(default=None, index=True)
    phone: str | None = None
    occupation: str | None = None           # what they do (e.g. trainer, job title)
    education: str | None = None
    address: str | None = None
    date_of_birth: date | None = None
    gender: Gender | None = None
    city: str | None = None
    emergency_contact: str | None = None    # name + phone of emergency contact

    # MFA (Section 5.5)
    mfa_enabled: bool = False
    mfa_secret: str | None = None  # Fernet ciphertext; decrypted only for TOTP checks.

    # Auth hardening (Section 5.7)
    failed_login_count: int = 0
    locked_until: datetime | None = None
    last_login_at: datetime | None = None

    # Last org the user logged into (B — last-used org auto-login).
    last_org_id: str | None = None

    is_active: bool = True
