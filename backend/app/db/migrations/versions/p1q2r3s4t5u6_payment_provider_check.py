"""Track when a pending card payment was last checked with its provider."""

from alembic import op
import sqlalchemy as sa

revision = "p1q2r3s4t5u6"
down_revision = "c2d3e4f5a6b7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("payments", sa.Column("provider_checked_at", sa.DateTime(), nullable=True))
    op.create_index("ix_payments_provider_checked_at", "payments", ["provider_checked_at"])


def downgrade() -> None:
    op.drop_index("ix_payments_provider_checked_at", table_name="payments")
    op.drop_column("payments", "provider_checked_at")
