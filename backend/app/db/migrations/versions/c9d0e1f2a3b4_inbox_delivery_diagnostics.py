"""Add truthful inbox message delivery diagnostics.

Revision ID: c9d0e1f2a3b4
Revises: b7c8d9e0f1a2
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "c9d0e1f2a3b4"
down_revision = "b7c8d9e0f1a2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("inbox_messages", sa.Column("delivery_error", sa.String(), nullable=True))
    op.execute(
        "UPDATE inbox_messages SET delivery_status = 'unknown' "
        "WHERE direction = 'outbound' AND delivery_status = 'sent'"
    )


def downgrade() -> None:
    op.drop_column("inbox_messages", "delivery_error")
