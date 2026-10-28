"""Password hashing, JWT issuance/verification, and password-policy checks.

Security rules enforced here (CLAUDE.md "Security Rules"):
  * Passwords: argon2 hashing; 12+ chars, mixed case, number, symbol.
  * JWTs: 15-min access, 7-day refresh, scoped to ONE organization_id.
"""

from __future__ import annotations

import hashlib
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

ACCESS = "access"
REFRESH = "refresh"
WEBSOCKET = "websocket"

# Password complexity (Section 4.2): 12+ chars, mixed case, number, symbol.
_PWD_MIN_LEN = 12
_SYMBOLS = re.compile(r"[^A-Za-z0-9]")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return pwd_context.verify(plain, hashed)
    except Exception:
        # A malformed or unrecognized stored hash must fail the login, not 500:
        # treating the candidate as non-matching is the safe, fail-closed result.
        return False


def password_complexity_errors(password: str) -> list[str]:
    """Return a list of human-readable policy violations (empty = OK)."""

    errors: list[str] = []
    if len(password) < _PWD_MIN_LEN:
        errors.append(f"Password must be at least {_PWD_MIN_LEN} characters.")
    if not re.search(r"[a-z]", password):
        errors.append("Password must contain a lowercase letter.")
    if not re.search(r"[A-Z]", password):
        errors.append("Password must contain an uppercase letter.")
    if not re.search(r"[0-9]", password):
        errors.append("Password must contain a number.")
    if not _SYMBOLS.search(password):
        errors.append("Password must contain a symbol.")
    return errors


def now_utc() -> datetime:
    # Naive UTC for portable comparisons across SQLite (returns naive) and
    # Postgres (timestamp without time zone). All app timestamps are UTC.
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _create_token(
    *,
    subject: str,
    org_id: str | None,
    role: str | None,
    token_type: str,
    expires_delta: timedelta,
    extra: dict[str, Any] | None = None,
) -> str:
    # Use aware UTC here: .timestamp() on a naive datetime assumes local time,
    # which would skew JWT iat/exp by the host's UTC offset. DB timestamps use
    # naive UTC (now_utc); JWT epoch must be true UTC.
    issued = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,
        "org_id": org_id,
        "role": role,
        "type": token_type,
        "iat": int(issued.timestamp()),
        "exp": int((issued + expires_delta).timestamp()),
        "jti": uuid.uuid4().hex,
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def create_access_token(
    *, user_id: str, org_id: str | None, role: str | None,
    remember: bool = False, session_id: str | None = None,
) -> str:
    minutes = (
        settings.remember_device_days * 24 * 60
        if remember
        else settings.access_token_expire_minutes
    )
    extra = {"session_id": session_id} if session_id else None
    return _create_token(
        subject=user_id,
        org_id=org_id,
        role=role,
        token_type=ACCESS,
        expires_delta=timedelta(minutes=minutes),
        extra=extra,
    )


def create_refresh_token(*, user_id: str, org_id: str | None, role: str | None) -> str:
    return _create_token(
        subject=user_id,
        org_id=org_id,
        role=role,
        token_type=REFRESH,
        expires_delta=timedelta(days=settings.refresh_token_expire_days),
    )


def create_websocket_ticket(
    *, user_id: str, org_id: str, role: str, session_id: str
) -> str:
    return _create_token(
        subject=user_id,
        org_id=org_id,
        role=role,
        token_type=WEBSOCKET,
        expires_delta=timedelta(seconds=30),
        extra={"session_id": session_id},
    )


def decode_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT. Raises JWTError on failure."""

    return jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])


def safe_decode(token: str) -> dict[str, Any] | None:
    try:
        return decode_token(token)
    except JWTError:
        return None


# -------------------------------------------------------------- random tokens
def generate_numeric_code(length: int = 6) -> str:
    """6-digit email verification code (Section 4.3)."""

    return "".join(secrets.choice("0123456789") for _ in range(length))


def generate_url_token(nbytes: int = 32) -> str:
    """Opaque single-use token for magic links / reset / invites."""

    return secrets.token_urlsafe(nbytes)


def hash_token(token: str) -> str:
    """Store only hashes of opaque tokens (sessions, reset links)."""

    return hashlib.sha256(token.encode()).hexdigest()
