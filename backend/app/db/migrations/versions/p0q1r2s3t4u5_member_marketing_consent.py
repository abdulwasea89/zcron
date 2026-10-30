"""Add channel-specific member marketing consent.

Revision ID: p0q1r2s3t4u5
Revises: o9p0q1r2s3t4
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "p0q1r2s3t4u5"
down_revision = "o9p0q1r2s3t4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for channel in ("email", "sms", "in_app"):
        op.add_column(
            "organization_members",
            sa.Column(f"marketing_{channel}_consent", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
        op.add_column(
            "organization_members",
            sa.Column(f"marketing_{channel}_consent_at", sa.DateTime(), nullable=True),
        )
        with op.batch_alter_table("organization_members") as batch:
            batch.alter_column(f"marketing_{channel}_consent", server_default=None)


def downgrade() -> None:
    for channel in ("in_app", "sms", "email"):
        op.drop_column("organization_members", f"marketing_{channel}_consent_at")
        op.drop_column("organization_members", f"marketing_{channel}_consent")
