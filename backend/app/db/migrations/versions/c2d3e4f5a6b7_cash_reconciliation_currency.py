"""Record the currency of new cash reconciliations."""

from alembic import op
import sqlalchemy as sa

revision = "c2d3e4f5a6b7"
down_revision = "b1c2d3e4f5a6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cash_reconciliations", sa.Column("currency", sa.String(length=3), nullable=True))
    op.add_column("cash_reconciliations", sa.Column("opening_float", sa.Float(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("cash_reconciliations", "opening_float")
    op.drop_column("cash_reconciliations", "currency")
