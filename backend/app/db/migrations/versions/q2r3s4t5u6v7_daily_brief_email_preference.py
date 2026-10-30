"""Add owner daily-brief email preference.

Revision ID: q2r3s4t5u6v7
Revises: q1r2s3t4u5v6
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "q2r3s4t5u6v7"
down_revision = "q1r2s3t4u5v6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "organization_members",
        sa.Column("daily_brief_email", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    with op.batch_alter_table("organization_members") as batch:
        batch.alter_column("daily_brief_email", server_default=None)


def downgrade() -> None:
    op.drop_column("organization_members", "daily_brief_email")
