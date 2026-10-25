"""Store immutable expense receipt evidence apart from ledger rows."""

from alembic import op
import sqlalchemy as sa

revision = "h0c1d2e3f4g5"
down_revision = "g9b0c1d2e3f4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "operating_expense_receipts",
        sa.Column("expense_id", sa.String(), nullable=False),
        sa.Column("organization_id", sa.String(), nullable=False),
        sa.Column("image_data", sa.LargeBinary(), nullable=False),
        sa.Column("media_type", sa.String(), nullable=False),
        sa.Column("sha256", sa.String(), nullable=False),
        sa.Column("uploaded_by", sa.String(), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("expense_id"),
        sa.ForeignKeyConstraint(["expense_id"], ["operating_expenses.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"]),
    )
    op.create_index("ix_operating_expense_receipts_organization_id", "operating_expense_receipts", ["organization_id"])


def downgrade() -> None:
    op.drop_index("ix_operating_expense_receipts_organization_id", table_name="operating_expense_receipts")
    op.drop_table("operating_expense_receipts")
