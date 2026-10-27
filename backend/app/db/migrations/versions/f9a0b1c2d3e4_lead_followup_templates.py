"""Store organization-specific lead follow-up email templates."""

from alembic import op
import sqlalchemy as sa

revision = "f9a0b1c2d3e4"
down_revision = "e8f9a0b1c2d3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column("lead_followup_templates", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.alter_column("organizations", "lead_followup_templates", server_default=None)


def downgrade() -> None:
    op.drop_column("organizations", "lead_followup_templates")
