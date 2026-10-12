"""create lead trial and tour bookings

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-10-12 00:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = "e4f5a6b7c8d9"
down_revision: str | None = "d3e4f5a6b7c8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "lead_bookings",
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("organization_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("lead_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("booking_type", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("class_session_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("trainer_member_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("starts_at", sa.DateTime(), nullable=False),
        sa.Column("ends_at", sa.DateTime(), nullable=True),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("notes", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("created_by", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("attended_at", sa.DateTime(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint("booking_type IN ('trial', 'tour')", name="ck_lead_booking_type"),
        sa.CheckConstraint(
            "(booking_type = 'trial' AND class_session_id IS NOT NULL) OR "
            "(booking_type = 'tour' AND class_session_id IS NULL)",
            name="ck_lead_booking_target",
        ),
        sa.CheckConstraint("ends_at IS NULL OR ends_at > starts_at", name="ck_lead_booking_time_range"),
        sa.CheckConstraint("status IN ('scheduled', 'attended', 'no_show', 'cancelled')", name="ck_lead_booking_status"),
        sa.ForeignKeyConstraint(["class_session_id"], ["class_sessions.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["trainer_member_id"], ["organization_members.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("lead_bookings", schema=None) as batch_op:
        batch_op.create_index("ix_lead_bookings_id", ["id"], unique=False)
        batch_op.create_index("ix_lead_bookings_organization_id", ["organization_id"], unique=False)
        batch_op.create_index("ix_lead_bookings_lead_id", ["lead_id"], unique=False)
        batch_op.create_index("ix_lead_bookings_booking_type", ["booking_type"], unique=False)
        batch_op.create_index("ix_lead_bookings_class_session_id", ["class_session_id"], unique=False)
        batch_op.create_index("ix_lead_bookings_starts_at", ["starts_at"], unique=False)
        batch_op.create_index("ix_lead_bookings_status", ["status"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("lead_bookings", schema=None) as batch_op:
        for name in ("status", "starts_at", "class_session_id", "booking_type", "lead_id", "organization_id", "id"):
            batch_op.drop_index(f"ix_lead_bookings_{name}")
    op.drop_table("lead_bookings")
