"""Add gym member invoices and payment links."""

from alembic import op
import sqlalchemy as sa

revision = "z3b4c5d6e7f8"
down_revision = "l4g5h6i7j8k9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "gym_invoices",
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("organization_id", sa.String(), nullable=False),
        sa.Column("member_id", sa.String(), nullable=False),
        sa.Column("invoice_number", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("issue_date", sa.Date(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("subtotal", sa.Numeric(14, 2), nullable=False),
        sa.Column("tax_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("total", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("notes", sa.String(), nullable=True),
        sa.Column("email_accepted", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["member_id"], ["organization_members.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "invoice_number", name="uq_gym_invoices_org_number"),
    )
    op.create_index("ix_gym_invoices_organization_id", "gym_invoices", ["organization_id"])
    op.create_index("ix_gym_invoices_member_id", "gym_invoices", ["member_id"])
    op.create_index("ix_gym_invoices_invoice_number", "gym_invoices", ["invoice_number"])
    op.create_index("ix_gym_invoices_status", "gym_invoices", ["status"])
    op.add_column("payments", sa.Column("gym_invoice_id", sa.String(), nullable=True))
    with op.batch_alter_table("payments") as batch:
        batch.create_foreign_key("fk_payments_gym_invoice_id", "gym_invoices", ["gym_invoice_id"], ["id"])
    op.create_index("ix_payments_gym_invoice_id", "payments", ["gym_invoice_id"])


def downgrade() -> None:
    op.drop_index("ix_payments_gym_invoice_id", table_name="payments")
    with op.batch_alter_table("payments") as batch:
        batch.drop_constraint("fk_payments_gym_invoice_id", type_="foreignkey")
        batch.drop_column("gym_invoice_id")
    for name in ("ix_gym_invoices_status", "ix_gym_invoices_invoice_number",
                 "ix_gym_invoices_member_id", "ix_gym_invoices_organization_id"):
        op.drop_index(name, table_name="gym_invoices")
    op.drop_table("gym_invoices")
