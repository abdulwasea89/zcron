"""Track Twilio status callbacks for campaign texts.

Revision ID: t6u7v8w9x0
Revises: s5t6u7v8w9x0
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "t6u7v8w9x0"
down_revision: str | None = "s5t6u7v8w9x0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("campaign_deliveries", sa.Column("provider_message_id", sa.String(), nullable=True))
    op.add_column("campaign_deliveries", sa.Column("delivery_status", sa.String(), nullable=True))
    op.create_index(
        op.f("ix_campaign_deliveries_provider_message_id"),
        "campaign_deliveries",
        ["provider_message_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_campaign_deliveries_provider_message_id"), table_name="campaign_deliveries")
    op.drop_column("campaign_deliveries", "delivery_status")
    op.drop_column("campaign_deliveries", "provider_message_id")
