"""add explicit consent and delivery tracking to lead follow-ups

Revision ID: f6a7b8c9d0e1
Revises: f5a6b7c8d9e0
Create Date: 2026-10-12 00:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "f6a7b8c9d0e1"
down_revision: str | None = "f5a6b7c8d9e0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "leads",
        sa.Column("email_followup_consent", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column("leads", sa.Column("email_followup_consent_at", sa.DateTime(), nullable=True))
    op.add_column(
        "lead_followups",
        sa.Column("email_status", sa.String(), server_default="skipped", nullable=False),
    )
    op.add_column("lead_followups", sa.Column("email_attempted_at", sa.DateTime(), nullable=True))
    op.add_column("lead_followups", sa.Column("email_sent_at", sa.DateTime(), nullable=True))
    op.add_column(
        "lead_followups",
        sa.Column("email_attempts", sa.Integer(), server_default="0", nullable=False),
    )
    with op.batch_alter_table("lead_followups", schema=None) as batch_op:
        batch_op.create_check_constraint(
            "ck_lead_followup_email_status",
            "email_status IN ('pending', 'sent', 'failed', 'skipped')",
        )
        batch_op.create_index("ix_lead_followups_email_status", ["email_status"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("lead_followups", schema=None) as batch_op:
        batch_op.drop_index("ix_lead_followups_email_status")
        batch_op.drop_constraint("ck_lead_followup_email_status", type_="check")
        batch_op.drop_column("email_attempts")
        batch_op.drop_column("email_sent_at")
        batch_op.drop_column("email_attempted_at")
        batch_op.drop_column("email_status")
    op.drop_column("leads", "email_followup_consent_at")
    op.drop_column("leads", "email_followup_consent")
