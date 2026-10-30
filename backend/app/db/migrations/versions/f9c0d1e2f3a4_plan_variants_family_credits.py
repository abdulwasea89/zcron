"""Add plan variants, household links and credit allowance snapshots.

Revision ID: f9c0d1e2f3a4
Revises: f8b9c0d1e2f3
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "f9c0d1e2f3a4"
down_revision: str | None = "f8b9c0d1e2f3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("membership_plans", sa.Column("audience", sa.String(), nullable=False, server_default="standard"))
    op.add_column("membership_plans", sa.Column("family_capacity", sa.Integer(), nullable=True))
    op.add_column("membership_plans", sa.Column("off_peak_start", sa.String(), nullable=True))
    op.add_column("membership_plans", sa.Column("off_peak_end", sa.String(), nullable=True))
    op.add_column("membership_plans", sa.Column("included_credits", sa.Integer(), nullable=True))
    op.add_column("organization_members", sa.Column("family_owner_member_id", sa.String(), nullable=True))
    op.create_index("ix_organization_members_family_owner_member_id", "organization_members", ["family_owner_member_id"])
    with op.batch_alter_table("organization_members") as batch:
        batch.create_foreign_key("fk_members_family_owner", "organization_members", ["family_owner_member_id"], ["id"])
    op.add_column("subscriptions", sa.Column("credits_allowance", sa.Integer(), nullable=True))
    op.add_column("attendance", sa.Column("credit_subscription_id", sa.String(), nullable=True))
    with op.batch_alter_table("attendance") as batch:
        batch.create_foreign_key("fk_attendance_credit_subscription", "subscriptions", ["credit_subscription_id"], ["id"])


def downgrade() -> None:
    with op.batch_alter_table("attendance") as batch:
        batch.drop_constraint("fk_attendance_credit_subscription", type_="foreignkey")
    op.drop_column("attendance", "credit_subscription_id")
    op.drop_column("subscriptions", "credits_allowance")
    with op.batch_alter_table("organization_members") as batch:
        batch.drop_constraint("fk_members_family_owner", type_="foreignkey")
    op.drop_index("ix_organization_members_family_owner_member_id", table_name="organization_members")
    op.drop_column("organization_members", "family_owner_member_id")
    for name in ("included_credits", "off_peak_end", "off_peak_start", "family_capacity", "audience"):
        op.drop_column("membership_plans", name)
