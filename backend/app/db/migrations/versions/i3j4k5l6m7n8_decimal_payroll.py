"""Store compensation and payroll money as fixed precision decimals.

Revision ID: i3j4k5l6m7n8
Revises: h2b3c4d5e6f7
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "i3j4k5l6m7n8"
down_revision = "h2b3c4d5e6f7"
branch_labels = None
depends_on = None


MONEY_COLUMNS = {
    "organization_members": (
        "fixed_monthly_salary",
        "hourly_rate",
        "per_class_rate",
    ),
    "payroll_runs": ("total_gross", "total_deductions", "total_net"),
    "payroll_entries": (
        "fixed",
        "hourly_amount",
        "class_amount",
        "commission_amount",
        "bonus",
        "deductions",
        "advance_repayment",
        "net",
    ),
    "pay_advances": ("amount", "repayment_per_period", "repaid_amount"),
}


def _alter_money_columns(*, target: sa.types.TypeEngine, source: sa.types.TypeEngine) -> None:
    for table, columns in MONEY_COLUMNS.items():
        with op.batch_alter_table(table) as batch:
            for column in columns:
                batch.alter_column(column, existing_type=source, type_=target)


def upgrade() -> None:
    # Numeric scale conversion rounds legacy float artifacts to the stored currency precision.
    _alter_money_columns(target=sa.Numeric(14, 2), source=sa.Float())
    for table, columns in MONEY_COLUMNS.items():
        for column in columns:
            op.execute(sa.text(f"UPDATE {table} SET {column} = ROUND({column}, 2)"))
    with op.batch_alter_table("organization_members") as batch:
        batch.alter_column("commission_rate", existing_type=sa.Float(), type_=sa.Numeric(8, 6))
    op.execute(
        sa.text("UPDATE organization_members SET commission_rate = ROUND(commission_rate, 6)")
    )


def downgrade() -> None:
    _alter_money_columns(target=sa.Float(), source=sa.Numeric(14, 2))
    with op.batch_alter_table("organization_members") as batch:
        batch.alter_column("commission_rate", existing_type=sa.Numeric(8, 6), type_=sa.Float())
