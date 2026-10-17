"""Add scheduled membership lifecycle and change billing details.

Revision ID: a2d3e4f5a6b7
Revises: a1c2d3e4f5a6
"""

from alembic import op
import sqlalchemy as sa

revision = "a2d3e4f5a6b7"
down_revision = "a1c2d3e4f5a6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("subscriptions", sa.Column("cancel_at_period_end", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("subscriptions", sa.Column("scheduled_plan_id", sa.String(), sa.ForeignKey("membership_plans.id"), nullable=True))
    op.add_column("subscriptions", sa.Column("scheduled_plan_at", sa.DateTime(), nullable=True))
    op.add_column("subscriptions", sa.Column("save_discount_percent", sa.Float(), nullable=False, server_default="0"))
    op.add_column("subscriptions", sa.Column("save_discount_expires_at", sa.DateTime(), nullable=True))
    op.add_column("membership_change_requests", sa.Column("offer_type", sa.String(), nullable=True))
    op.add_column("membership_change_requests", sa.Column("offer_plan_id", sa.String(), sa.ForeignKey("membership_plans.id"), nullable=True))
    op.add_column("membership_change_requests", sa.Column("offer_discount_percent", sa.Float(), nullable=True))
    op.add_column("membership_change_requests", sa.Column("offer_discount_months", sa.Integer(), nullable=True))
    op.add_column("membership_change_requests", sa.Column("amount_due", sa.Float(), nullable=False, server_default="0"))
    op.add_column("membership_change_requests", sa.Column("payment_id", sa.String(), sa.ForeignKey("payments.id"), nullable=True))
    op.add_column("membership_change_requests", sa.Column("effective_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("membership_change_requests", "effective_at")
    op.drop_column("membership_change_requests", "payment_id")
    op.drop_column("membership_change_requests", "amount_due")
    op.drop_column("membership_change_requests", "offer_discount_months")
    op.drop_column("membership_change_requests", "offer_discount_percent")
    op.drop_column("membership_change_requests", "offer_plan_id")
    op.drop_column("membership_change_requests", "offer_type")
    op.drop_column("subscriptions", "save_discount_expires_at")
    op.drop_column("subscriptions", "save_discount_percent")
    op.drop_column("subscriptions", "scheduled_plan_at")
    op.drop_column("subscriptions", "scheduled_plan_id")
    op.drop_column("subscriptions", "cancel_at_period_end")
