"""Persist receipt evidence for authorized staff review.

Revision ID: h2b3c4d5e6f7
Revises: g1a2b3c4d5e6
"""

from alembic import op
import sqlalchemy as sa

revision = "h2b3c4d5e6f7"
down_revision = "g1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("receipt_uploads", sa.Column("image_data", sa.LargeBinary(), nullable=True))
    op.add_column("receipt_uploads", sa.Column("image_media_type", sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column("receipt_uploads", "image_media_type")
    op.drop_column("receipt_uploads", "image_data")
