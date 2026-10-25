"""Track first-contact delivery receipts and source conversions.

Revision ID: x0y1z2a3b4c5
Revises: w9x0y1z2a3b4
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "x0y1z2a3b4c5"
down_revision: str | None = "w9x0y1z2a3b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("leads") as batch:
        batch.add_column(sa.Column(
            "first_contact_delivery_status", sa.String(), nullable=False, server_default="unknown",
        ))
        batch.add_column(sa.Column("first_contact_external_id", sa.String(), nullable=True))
        batch.create_index("ix_leads_first_contact_external_id", ["first_contact_external_id"])


def downgrade() -> None:
    with op.batch_alter_table("leads") as batch:
        batch.drop_index("ix_leads_first_contact_external_id")
        batch.drop_column("first_contact_external_id")
        batch.drop_column("first_contact_delivery_status")
