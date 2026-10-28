"""TOTP MFA enrollment & verification (Section 5.5).

Flow:
  1. ``begin_enrollment`` — generate a TOTP secret, store it provisionally on the
     user (``mfa_secret`` set, ``mfa_enabled`` still False), and return the
     ``otpauth://`` provisioning URI + the current code (stub aid for local dev).
  2. ``confirm_enrollment`` — user submits a code from their app; on success
     ``mfa_enabled`` flips True. MFA is now required at login.
  3. ``disable`` — turn MFA off (clears secret).

Login enforcement lives in ``auth_service.login``: when ``user.mfa_enabled`` and
no valid ``mfa_code`` is supplied, login returns ``requires_mfa=True`` with no
tokens; the client re-submits with the code. Enterprise orgs set
``mfa_required`` on the org, which can force enrollment in the UI.
"""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import totp
from app.core.mfa_encryption import decrypt_mfa_secret, encrypt_mfa_secret
from app.core.security import now_utc, verify_password
from app.models.user import User
from app.services.audit_service import record_audit


async def begin_enrollment(session: AsyncSession, *, user: User, issuer: str) -> dict:
    """Generate (or regenerate) a provisional secret. Does not enable MFA yet."""

    if user.mfa_enabled:
        raise HTTPException(status_code=409, detail="MFA is already enabled.")
    secret = totp.generate_secret()
    user.mfa_secret = encrypt_mfa_secret(secret)
    session.add(user)
    await record_audit(session, action="mfa.enroll_started", actor_user_id=user.id,
                       entity_type="user", entity_id=user.id)
    return {
        "secret": secret,
        "otpauth_uri": totp.provisioning_uri(secret, account_name=user.email, issuer=issuer),
    }


async def confirm_enrollment(session: AsyncSession, *, user: User, code: str) -> None:
    """Verify a code against the provisional secret and enable MFA."""

    if not user.mfa_secret:
        raise HTTPException(status_code=409, detail="Start MFA enrollment first.")
    if not totp.verify(decrypt_mfa_secret(user.mfa_secret), code, for_time=now_utc()):
        raise HTTPException(status_code=400, detail="Invalid MFA code.")
    user.mfa_enabled = True
    session.add(user)
    await record_audit(session, action="mfa.enabled", actor_user_id=user.id,
                       entity_type="user", entity_id=user.id)


async def disable(session: AsyncSession, *, user: User, password: str) -> None:
    """Disable MFA. Re-auth with the password (sensitive action, Section 5.6)."""

    if not verify_password(password, user.hashed_password):
        raise HTTPException(status_code=403, detail="Password is incorrect.")
    user.mfa_enabled = False
    user.mfa_secret = None
    session.add(user)
    await record_audit(session, action="mfa.disabled", actor_user_id=user.id,
                       entity_type="user", entity_id=user.id)


def check_code(user: User, code: str | None) -> bool:
    """True if MFA is satisfied: not enabled, or a valid code is supplied."""

    if not user.mfa_enabled:
        return True
    if not code:
        return False
    return bool(user.mfa_secret) and totp.verify(
        decrypt_mfa_secret(user.mfa_secret), code, for_time=now_utc()
    )
