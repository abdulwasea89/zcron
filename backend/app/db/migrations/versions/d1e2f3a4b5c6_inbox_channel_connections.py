"""Persist encrypted per-workspace inbox provider connections.

Revision ID: d1e2f3a4b5c6
Revises: c9d0e1f2a3b4
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "d1e2f3a4b5c6"
down_revision = "c9d0e1f2a3b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "inbox_channel_connections",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("organization_id", sa.String(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("channel", sa.String(), nullable=False),
        sa.Column("credentials_ciphertext", sa.String(), nullable=False),
        sa.Column("webhook_token", sa.String(), nullable=True),
        sa.Column("connected_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("organization_id", "channel", name="uq_inbox_channel_org_channel"),
    )
    op.create_index("ix_inbox_channel_connections_id", "inbox_channel_connections", ["id"], unique=True)
    op.create_index("ix_inbox_channel_connections_organization_id", "inbox_channel_connections", ["organization_id"])
    op.create_index("ix_inbox_channel_connections_channel", "inbox_channel_connections", ["channel"])
    op.create_index("ix_inbox_channel_connections_connected_at", "inbox_channel_connections", ["connected_at"])


def downgrade() -> None:
    op.drop_index("ix_inbox_channel_connections_id", table_name="inbox_channel_connections")
    op.drop_index("ix_inbox_channel_connections_connected_at", table_name="inbox_channel_connections")
    op.drop_index("ix_inbox_channel_connections_channel", table_name="inbox_channel_connections")
    op.drop_index("ix_inbox_channel_connections_organization_id", table_name="inbox_channel_connections")
    op.drop_table("inbox_channel_connections")
