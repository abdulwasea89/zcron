"""Add tenant-scoped operating expense ledger."""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
import sqlmodel

revision: str = "w9x0y1z2a3b4"
down_revision: str | None = "v8w9x0y1z2a3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "operating_expenses",
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("organization_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("category", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("description", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("vendor", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sqlmodel.sql.sqltypes.AutoString(length=3), nullable=False),
        sa.Column("incurred_on", sa.Date(), nullable=False),
        sa.Column("created_by", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("voided_at", sa.DateTime(), nullable=True),
        sa.Column("voided_by", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("void_reason", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.CheckConstraint("amount > 0", name="ck_operating_expenses_positive_amount"),
        sa.CheckConstraint("length(currency) = 3", name="ck_operating_expenses_currency_length"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["voided_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("operating_expenses") as batch_op:
        batch_op.create_index("ix_operating_expenses_id", ["id"])
        batch_op.create_index("ix_operating_expenses_organization_id", ["organization_id"])
        batch_op.create_index("ix_operating_expenses_category", ["category"])
        batch_op.create_index("ix_operating_expenses_currency", ["currency"])
        batch_op.create_index("ix_operating_expenses_incurred_on", ["incurred_on"])


def downgrade() -> None:
    with op.batch_alter_table("operating_expenses") as batch_op:
        batch_op.drop_index("ix_operating_expenses_incurred_on")
        batch_op.drop_index("ix_operating_expenses_currency")
        batch_op.drop_index("ix_operating_expenses_category")
        batch_op.drop_index("ix_operating_expenses_organization_id")
        batch_op.drop_index("ix_operating_expenses_id")
    op.drop_table("operating_expenses")
