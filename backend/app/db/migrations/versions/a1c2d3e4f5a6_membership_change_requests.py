"""Add member plan change and cancellation requests.

Revision ID: a1c2d3e4f5a6
Revises: fbe3d4c5a6b7
"""

from alembic import op
import sqlalchemy as sa

revision = "a1c2d3e4f5a6"
down_revision = "fbe3d4c5a6b7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "membership_change_requests",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("organization_id", sa.String(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("member_id", sa.String(), sa.ForeignKey("organization_members.id"), nullable=False),
        sa.Column("subscription_id", sa.String(), sa.ForeignKey("subscriptions.id"), nullable=False),
        sa.Column("request_type", sa.String(), nullable=False),
        sa.Column("target_plan_id", sa.String(), sa.ForeignKey("membership_plans.id"), nullable=True),
        sa.Column("reason", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("save_offer", sa.String(length=500), nullable=True),
        sa.Column("reviewed_by", sa.String(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("decision_note", sa.String(length=500), nullable=True),
    )
    for column in ("organization_id", "member_id", "subscription_id", "request_type", "status"):
        op.create_index(f"ix_membership_change_requests_{column}", "membership_change_requests", [column])


def downgrade() -> None:
    for column in ("status", "request_type", "subscription_id", "member_id", "organization_id"):
        op.drop_index(f"ix_membership_change_requests_{column}", table_name="membership_change_requests")
    op.drop_table("membership_change_requests")
