"""Store per-staff payout reconciliation evidence.

Revision ID: m7n8o9p0q1r2
Revises: l6m7n8o9p0q1
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "m7n8o9p0q1r2"
down_revision = "l6m7n8o9p0q1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("payroll_entries", sa.Column("paid_at", sa.DateTime(), nullable=True))
    op.add_column("payroll_entries", sa.Column("payout_reference", sa.String(), nullable=True))
    op.add_column("payroll_entries", sa.Column("paid_amount", sa.Numeric(14, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("payroll_entries", "paid_amount")
    op.drop_column("payroll_entries", "payout_reference")
    op.drop_column("payroll_entries", "paid_at")
