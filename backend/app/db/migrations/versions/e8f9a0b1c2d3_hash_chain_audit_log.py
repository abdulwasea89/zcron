"""Add per-organization audit hash chains."""

from alembic import op
import sqlalchemy as sa

revision = "e8f9a0b1c2d3"
down_revision = "z3b4c5d6e7f8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("organizations", sa.Column("audit_chain_head", sa.String(length=64), nullable=True))
    op.add_column("audit_logs", sa.Column("previous_hash", sa.String(length=64), nullable=True))
    op.add_column("audit_logs", sa.Column("entry_hash", sa.String(length=64), nullable=True))
    op.create_index("ix_audit_logs_entry_hash", "audit_logs", ["entry_hash"])


def downgrade() -> None:
    op.drop_index("ix_audit_logs_entry_hash", table_name="audit_logs")
    op.drop_column("audit_logs", "entry_hash")
    op.drop_column("audit_logs", "previous_hash")
    op.drop_column("organizations", "audit_chain_head")
