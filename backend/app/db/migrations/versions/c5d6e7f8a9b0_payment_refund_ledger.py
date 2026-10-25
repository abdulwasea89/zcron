"""Keep dated refund movements for accounting periods."""

from alembic import op
import sqlalchemy as sa

revision = "c5d6e7f8a9b0"
down_revision = "b4c5d6e7f8a9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "payment_refunds",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("organization_id", sa.String(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("payment_id", sa.String(), sa.ForeignKey("payments.id"), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.String(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("actor_user_id", sa.String(), sa.ForeignKey("users.id"), nullable=True),
        sa.CheckConstraint("amount > 0", name="ck_payment_refund_positive"),
    )
    for column in ("id", "organization_id", "payment_id", "currency", "occurred_at"):
        op.create_index(f"ix_payment_refunds_{column}", "payment_refunds", [column])


def downgrade() -> None:
    op.drop_table("payment_refunds")
