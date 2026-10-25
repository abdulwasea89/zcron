"""Require a recorded outreach attempt for lead response metrics.

Revision ID: s5t6u7v8w9x0
Revises: r4s5t6u7v8w9
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "s5t6u7v8w9x0"
down_revision: str | None = "r4s5t6u7v8w9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "leads",
        sa.Column("first_contact_logged", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("leads", "first_contact_logged")
