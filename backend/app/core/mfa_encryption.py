"""Encrypt TOTP secrets stored in the user table."""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet

from app.core.config import settings

_PREFIX = "enc:v1:"


def _fernet() -> Fernet:
    key = settings.mfa_encryption_key
    if not key and settings.app_env.strip().lower() not in {"prod", "production"}:
        key = base64.urlsafe_b64encode(
            hashlib.sha256(b"acron:mfa:" + settings.secret_key.encode()).digest()
        ).decode()
    if not key:
        raise RuntimeError("MFA_ENCRYPTION_KEY must be configured.")
    return Fernet(key.encode())


def encrypt_mfa_secret(secret: str) -> str:
    return _PREFIX + _fernet().encrypt(secret.encode()).decode()


def decrypt_mfa_secret(secret: str) -> str:
    if not secret.startswith(_PREFIX):
        if settings.app_env.strip().lower() in {"prod", "production"}:
            raise RuntimeError("The MFA secret is not encrypted; apply the MFA encryption migration.")
        return secret
    return _fernet().decrypt(secret.removeprefix(_PREFIX).encode()).decode()
