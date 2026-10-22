"""Add planned staff shifts, separate from clock records.

Revision ID: j4k5l6m7n8o9
Revises: i3j4k5l6m7n8
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "j4k5l6m7n8o9"
down_revision = "i3j4k5l6m7n8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scheduled_shifts",
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("organization_id", sa.String(), nullable=False),
        sa.Column("staff_member_id", sa.String(), nullable=False),
        sa.Column("starts_at", sa.DateTime(), nullable=False),
        sa.Column("ends_at", sa.DateTime(), nullable=False),
        sa.Column("note", sa.String(), nullable=True),
        sa.Column("assigned_by", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["assigned_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["staff_member_id"], ["organization_members.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_scheduled_shifts_id", "scheduled_shifts", ["id"])
    op.create_index("ix_scheduled_shifts_organization_id", "scheduled_shifts", ["organization_id"])
    op.create_index("ix_scheduled_shifts_staff_member_id", "scheduled_shifts", ["staff_member_id"])
    op.create_index("ix_scheduled_shifts_starts_at", "scheduled_shifts", ["starts_at"])


def downgrade() -> None:
    op.drop_index("ix_scheduled_shifts_starts_at", table_name="scheduled_shifts")
    op.drop_index("ix_scheduled_shifts_staff_member_id", table_name="scheduled_shifts")
    op.drop_index("ix_scheduled_shifts_organization_id", table_name="scheduled_shifts")
    op.drop_index("ix_scheduled_shifts_id", table_name="scheduled_shifts")
    op.drop_table("scheduled_shifts")
