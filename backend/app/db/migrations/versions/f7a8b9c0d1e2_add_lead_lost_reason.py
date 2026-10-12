"""add controlled lost reasons to leads

Revision ID: f7a8b9c0d1e2
Revises: f6a7b8c9d0e1
Create Date: 2026-10-12 00:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "f7a8b9c0d1e2"
down_revision: str | None = "f6a7b8c9d0e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("leads", sa.Column("lost_reason", sa.String(), nullable=True))
    with op.batch_alter_table("leads", schema=None) as batch_op:
        batch_op.create_check_constraint(
            "ck_leads_lost_reason",
            "lost_reason IS NULL OR lost_reason IN "
            "('price', 'schedule', 'timing', 'location', 'joined_elsewhere', 'no_response', 'not_interested', 'other')",
        )
        batch_op.create_index("ix_leads_lost_reason", ["lost_reason"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("leads", schema=None) as batch_op:
        batch_op.drop_index("ix_leads_lost_reason")
        batch_op.drop_constraint("ck_leads_lost_reason", type_="check")
        batch_op.drop_column("lost_reason")
