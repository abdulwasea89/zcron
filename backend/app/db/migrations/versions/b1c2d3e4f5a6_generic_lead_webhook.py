"""Add a per-gym authenticated webhook for external lead forms."""

from alembic import op
import sqlalchemy as sa

revision = "b1c2d3e4f5a6"
down_revision = "a0b1c2d3e4f5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("organizations", sa.Column("lead_capture_webhook_token", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("organizations", "lead_capture_webhook_token")
