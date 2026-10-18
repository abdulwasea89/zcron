"""Store Stripe decline classification for dunning and staff recovery.

Revision ID: g1a2b3c4d5e6
Revises: f3a4b5c6d7e8
"""

from alembic import op
import sqlalchemy as sa

revision = "g1a2b3c4d5e6"
down_revision = "f3a4b5c6d7e8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("payments", sa.Column("stripe_failure_code", sa.String(length=64), nullable=True))
    op.add_column("payments", sa.Column("stripe_failure_decline_code", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("payments", "stripe_failure_decline_code")
    op.drop_column("payments", "stripe_failure_code")
