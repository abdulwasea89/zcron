"""Track explicit SMS permission for lead follow-up.

Revision ID: n8o9p0q1r2s3
Revises: m7n8o9p0q1r2
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "n8o9p0q1r2s3"
down_revision = "m7n8o9p0q1r2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("leads", sa.Column("sms_followup_consent", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("leads", sa.Column("sms_followup_consent_at", sa.DateTime(), nullable=True))
    with op.batch_alter_table("leads") as batch:
        batch.alter_column("sms_followup_consent", server_default=None)


def downgrade() -> None:
    op.drop_column("leads", "sms_followup_consent_at")
    op.drop_column("leads", "sms_followup_consent")
