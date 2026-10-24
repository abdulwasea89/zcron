"""Store social inbox handles on gym leads.

Revision ID: q1r2s3t4u5v6
Revises: p0q1r2s3t4u5
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "q1r2s3t4u5v6"
down_revision = "p0q1r2s3t4u5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("leads", sa.Column("contact_handle", sa.String(length=256), nullable=True))
    op.create_index(
        "ix_leads_org_source_contact_handle", "leads",
        ["organization_id", "source", "contact_handle"], unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_leads_org_source_contact_handle", table_name="leads")
    op.drop_column("leads", "contact_handle")
