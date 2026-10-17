"""Add required owner onboarding and hosted checkout tracking.

Revision ID: a3e4f5a6b7c8
Revises: a2d3e4f5a6b7
"""

from alembic import op
import sqlalchemy as sa

revision = "a3e4f5a6b7c8"
down_revision = "a2d3e4f5a6b7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column("onboarding_complete", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column("organizations", sa.Column("stripe_onboarding_session_id", sa.String(), nullable=True))
    op.add_column("organizations", sa.Column("stripe_onboarding_attempt", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("organizations", "stripe_onboarding_session_id")
    op.drop_column("organizations", "stripe_onboarding_attempt")
    op.drop_column("organizations", "onboarding_complete")
