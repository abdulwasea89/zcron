"""Add the waitlisted class booking state.

Revision ID: k5l6m7n8o9p0
Revises: j4k5l6m7n8o9
"""

from __future__ import annotations

from alembic import op


revision = "k5l6m7n8o9p0"
down_revision = "j4k5l6m7n8o9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TYPE bookingstatus ADD VALUE IF NOT EXISTS 'WAITLISTED'")


def downgrade() -> None:
    # PostgreSQL enum values are intentionally retained; deleting one requires
    # rebuilding the enum and rewriting any bookings created while this ran.
    pass
