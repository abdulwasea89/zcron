"""Add trainer workout/session logs.

Revision ID: l6m7n8o9p0q1
Revises: k5l6m7n8o9p0
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "l6m7n8o9p0q1"
down_revision = "k5l6m7n8o9p0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "trainer_session_logs",
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("organization_id", sa.String(), nullable=False),
        sa.Column("trainer_member_id", sa.String(), nullable=False),
        sa.Column("client_member_id", sa.String(), nullable=False),
        sa.Column("performed_at", sa.DateTime(), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("focus", sa.String(), nullable=False),
        sa.Column("notes", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["trainer_member_id"], ["organization_members.id"]),
        sa.ForeignKeyConstraint(["client_member_id"], ["organization_members.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_trainer_session_logs_id", "trainer_session_logs", ["id"])
    op.create_index("ix_trainer_session_logs_organization_id", "trainer_session_logs", ["organization_id"])
    op.create_index("ix_trainer_session_logs_trainer_member_id", "trainer_session_logs", ["trainer_member_id"])
    op.create_index("ix_trainer_session_logs_client_member_id", "trainer_session_logs", ["client_member_id"])
    op.create_index("ix_trainer_session_logs_performed_at", "trainer_session_logs", ["performed_at"])


def downgrade() -> None:
    op.drop_index("ix_trainer_session_logs_performed_at", table_name="trainer_session_logs")
    op.drop_index("ix_trainer_session_logs_client_member_id", table_name="trainer_session_logs")
    op.drop_index("ix_trainer_session_logs_trainer_member_id", table_name="trainer_session_logs")
    op.drop_index("ix_trainer_session_logs_organization_id", table_name="trainer_session_logs")
    op.drop_index("ix_trainer_session_logs_id", table_name="trainer_session_logs")
    op.drop_table("trainer_session_logs")
