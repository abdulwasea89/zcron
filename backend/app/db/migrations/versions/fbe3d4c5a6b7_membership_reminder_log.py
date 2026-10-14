"""Add idempotent membership reminder records.

Revision ID: fbe3d4c5a6b7
Revises: fad2e3f4a5b6
"""

from alembic import op
import sqlalchemy as sa

revision = "fbe3d4c5a6b7"
down_revision = "fad2e3f4a5b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "membership_reminders",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("organization_id", sa.String(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("subscription_id", sa.String(), sa.ForeignKey("subscriptions.id"), nullable=False),
        sa.Column("period_end", sa.DateTime(), nullable=False),
        sa.Column("stage", sa.String(), nullable=False),
        sa.Column("sent_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("subscription_id", "period_end", "stage", name="uq_membership_reminder_cycle_stage"),
    )
    op.create_index("ix_membership_reminders_organization_id", "membership_reminders", ["organization_id"])
    op.create_index("ix_membership_reminders_subscription_id", "membership_reminders", ["subscription_id"])
    op.create_index("ix_membership_reminders_stage", "membership_reminders", ["stage"])


def downgrade() -> None:
    op.drop_index("ix_membership_reminders_stage", table_name="membership_reminders")
    op.drop_index("ix_membership_reminders_subscription_id", table_name="membership_reminders")
    op.drop_index("ix_membership_reminders_organization_id", table_name="membership_reminders")
    op.drop_table("membership_reminders")
