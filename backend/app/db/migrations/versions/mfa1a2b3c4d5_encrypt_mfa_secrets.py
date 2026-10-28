"""Encrypt TOTP secrets stored in user records.

Revision ID: mfa1a2b3c4d5
Revises: a6b7c8d9e0f1
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

from app.core.mfa_encryption import decrypt_mfa_secret, encrypt_mfa_secret


revision = "mfa1a2b3c4d5"
down_revision = "a6b7c8d9e0f1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text("SELECT id, mfa_secret FROM users WHERE mfa_secret IS NOT NULL")
    )
    for user_id, secret in rows:
        if not secret.startswith("enc:v1:"):
            connection.execute(
                sa.text("UPDATE users SET mfa_secret = :secret WHERE id = :user_id"),
                {"secret": encrypt_mfa_secret(secret), "user_id": user_id},
            )


def downgrade() -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text("SELECT id, mfa_secret FROM users WHERE mfa_secret LIKE 'enc:v1:%'")
    )
    for user_id, secret in rows:
        connection.execute(
            sa.text("UPDATE users SET mfa_secret = :secret WHERE id = :user_id"),
            {"secret": decrypt_mfa_secret(secret), "user_id": user_id},
        )
