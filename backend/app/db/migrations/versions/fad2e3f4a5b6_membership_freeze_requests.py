"""Add member initiated membership freeze requests and pause metadata.

Revision ID: fad2e3f4a5b6
Revises: fac1d2e3f4a5
"""

from alembic import op
import sqlalchemy as sa

revision = "fad2e3f4a5b6"
down_revision = "fac1d2e3f4a5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("organization_members", sa.Column("status_before_freeze", sa.String(), nullable=True))
    op.add_column("subscriptions", sa.Column("frozen_at", sa.DateTime(), nullable=True))
    op.add_column("subscriptions", sa.Column("status_before_freeze", sa.String(), nullable=True))
    op.create_table(
        "membership_freeze_requests",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("organization_id", sa.String(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("member_id", sa.String(), sa.ForeignKey("organization_members.id"), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=False),
        sa.Column("requested_until", sa.DateTime(), nullable=True),
        sa.Column("source", sa.String(), nullable=False, server_default="member"),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("reviewed_by", sa.String(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("decision_note", sa.String(length=500), nullable=True),
    )
    op.create_index("ix_membership_freeze_requests_organization_id", "membership_freeze_requests", ["organization_id"])
    op.create_index("ix_membership_freeze_requests_member_id", "membership_freeze_requests", ["member_id"])
    op.create_index("ix_membership_freeze_requests_source", "membership_freeze_requests", ["source"])
    op.create_index("ix_membership_freeze_requests_status", "membership_freeze_requests", ["status"])


def downgrade() -> None:
    op.drop_index("ix_membership_freeze_requests_status", table_name="membership_freeze_requests")
    op.drop_index("ix_membership_freeze_requests_source", table_name="membership_freeze_requests")
    op.drop_index("ix_membership_freeze_requests_member_id", table_name="membership_freeze_requests")
    op.drop_index("ix_membership_freeze_requests_organization_id", table_name="membership_freeze_requests")
    op.drop_table("membership_freeze_requests")
    op.drop_column("subscriptions", "status_before_freeze")
    op.drop_column("subscriptions", "frozen_at")
    op.drop_column("organization_members", "status_before_freeze")
