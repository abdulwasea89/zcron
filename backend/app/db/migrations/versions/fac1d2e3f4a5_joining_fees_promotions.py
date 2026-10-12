"""Add joining fees, promotions and immutable payment price components.

Revision ID: fac1d2e3f4a5
Revises: f9c0d1e2f3a4
"""

from alembic import op
import sqlalchemy as sa

revision = "fac1d2e3f4a5"
down_revision = "f9c0d1e2f3a4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("membership_plans", sa.Column("joining_fee", sa.Float(), nullable=False, server_default="0"))
    op.add_column("payments", sa.Column("plan_price_amount", sa.Float(), nullable=True))
    op.add_column("payments", sa.Column("joining_fee_amount", sa.Float(), nullable=False, server_default="0"))
    op.add_column("payments", sa.Column("discount_amount", sa.Float(), nullable=False, server_default="0"))
    op.add_column("payments", sa.Column("promo_code", sa.String(), nullable=True))
    op.create_table(
        "promotions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("organization_id", sa.String(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("plan_id", sa.String(), sa.ForeignKey("membership_plans.id"), nullable=True),
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("discount_type", sa.String(), nullable=False),
        sa.Column("discount_value", sa.Float(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("starts_at", sa.DateTime(), nullable=True),
        sa.Column("ends_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("organization_id", "code", name="uq_promotions_org_code"),
    )
    op.create_index("ix_promotions_organization_id", "promotions", ["organization_id"])
    op.create_index("ix_promotions_code", "promotions", ["code"])


def downgrade() -> None:
    op.drop_index("ix_promotions_code", table_name="promotions")
    op.drop_index("ix_promotions_organization_id", table_name="promotions")
    op.drop_table("promotions")
    for name in ("promo_code", "discount_amount", "joining_fee_amount", "plan_price_amount"):
        op.drop_column("payments", name)
    op.drop_column("membership_plans", "joining_fee")
