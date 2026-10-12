"""Add organization-scoped member profile details.

Revision ID: f8b9c0d1e2f3
Revises: f7a8b9c0d1e2
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "f8b9c0d1e2f3"
down_revision: str | None = "f7a8b9c0d1e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    for name in ("goals", "health_notes", "id_document_type", "id_document_last4"):
        op.add_column("organization_members", sa.Column(name, sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("organization_members") as batch_op:
        for name in ("id_document_last4", "id_document_type", "health_notes", "goals"):
            batch_op.drop_column(name)
