"""Add member privacy request records.

Revision ID: o9p0q1r2s3t4
Revises: n8o9p0q1r2s3
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "o9p0q1r2s3t4"
down_revision = "n8o9p0q1r2s3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "data_subject_requests",
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("organization_id", sa.String(), nullable=False),
        sa.Column("member_id", sa.String(), nullable=False),
        sa.Column("member_name", sa.String(), nullable=False),
        sa.Column("member_email", sa.String(), nullable=False),
        sa.Column("request_type", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("note", sa.String(), nullable=True),
        sa.Column("resolution_note", sa.String(), nullable=True),
        sa.Column("erasure_redacted_at", sa.DateTime(), nullable=True),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column("resolved_by", sa.String(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["resolved_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_data_subject_requests_id", "data_subject_requests", ["id"])
    op.create_index("ix_data_subject_requests_organization_id", "data_subject_requests", ["organization_id"])
    op.create_index("ix_data_subject_requests_member_id", "data_subject_requests", ["member_id"])
    op.create_index("ix_data_subject_requests_request_type", "data_subject_requests", ["request_type"])
    op.create_index("ix_data_subject_requests_status", "data_subject_requests", ["status"])


def downgrade() -> None:
    op.drop_index("ix_data_subject_requests_status", table_name="data_subject_requests")
    op.drop_index("ix_data_subject_requests_request_type", table_name="data_subject_requests")
    op.drop_index("ix_data_subject_requests_member_id", table_name="data_subject_requests")
    op.drop_index("ix_data_subject_requests_organization_id", table_name="data_subject_requests")
    op.drop_index("ix_data_subject_requests_id", table_name="data_subject_requests")
    op.drop_table("data_subject_requests")
