"""Add retail inventory and stock movement history."""
from alembic import op
import sqlalchemy as sa

revision = "o3p4q5r6s7t8"
down_revision = "n2o3p4q5r6s7"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "retail_products",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("organization_id", sa.String(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("sku", sa.String(80), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("price_minor", sa.Integer(), nullable=False),
        sa.Column("stock_quantity", sa.Integer(), nullable=False),
        sa.Column("low_stock_threshold", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("organization_id", "sku", name="uq_retail_product_org_sku"),
        sa.CheckConstraint("stock_quantity >= 0", name="ck_retail_stock_nonnegative"),
        sa.CheckConstraint("price_minor >= 0", name="ck_retail_price_nonnegative"),
        sa.CheckConstraint("low_stock_threshold >= 0", name="ck_retail_threshold_nonnegative"),
    )
    op.create_index("ix_retail_products_id", "retail_products", ["id"])
    op.create_index("ix_retail_products_organization_id", "retail_products", ["organization_id"])
    op.create_table(
        "retail_stock_movements",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("organization_id", sa.String(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("product_id", sa.String(), sa.ForeignKey("retail_products.id"), nullable=False),
        sa.Column("actor_user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("quantity_delta", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(240), nullable=False),
        sa.CheckConstraint("quantity_delta != 0", name="ck_retail_movement_nonzero"),
    )
    for column in ("id", "organization_id", "product_id"):
        op.create_index(f"ix_retail_stock_movements_{column}", "retail_stock_movements", [column])
    if op.get_bind().dialect.name == "postgresql":
        for table in ("retail_products", "retail_stock_movements"):
            op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
            op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
            op.execute(
                f"CREATE POLICY acron_tenant_scope ON {table} FOR ALL "
                "USING (current_setting('app.rls_bypass', true) = 'on' OR "
                "organization_id::text = nullif(current_setting('app.organization_id', true), '')) "
                "WITH CHECK (current_setting('app.rls_bypass', true) = 'on' OR "
                "organization_id::text = nullif(current_setting('app.organization_id', true), ''))"
            )


def downgrade():
    op.drop_table("retail_stock_movements")
    op.drop_table("retail_products")
