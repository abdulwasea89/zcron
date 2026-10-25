"""Track estimated campaign cost and explicit payment attribution."""

from alembic import op
import sqlalchemy as sa

revision = "e7f8a9b0c1d2"
down_revision = "d6e7f8a9b0c1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("campaigns", sa.Column("estimated_unit_cost", sa.Numeric(14, 6), nullable=True))
    op.add_column("campaigns", sa.Column("cost_currency", sa.String(), nullable=False, server_default="USD"))
    op.create_table("campaign_payment_attributions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("organization_id", sa.String(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("campaign_id", sa.String(), sa.ForeignKey("campaigns.id"), nullable=False),
        sa.Column("payment_id", sa.String(), sa.ForeignKey("payments.id"), nullable=False),
        sa.Column("attributed_by", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.UniqueConstraint("payment_id", name="uq_campaign_attribution_payment"),
    )
    for column in ("id", "organization_id", "campaign_id", "payment_id"):
        op.create_index(f"ix_campaign_payment_attributions_{column}", "campaign_payment_attributions", [column])


def downgrade() -> None:
    op.drop_table("campaign_payment_attributions")
    with op.batch_alter_table("campaigns") as batch:
        batch.drop_column("cost_currency")
        batch.drop_column("estimated_unit_cost")
