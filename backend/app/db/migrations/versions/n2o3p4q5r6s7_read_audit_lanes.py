"""Separate chained privacy reads into per-actor audit lanes."""

from alembic import op
import sqlalchemy as sa


revision = "n2o3p4q5r6s7"
down_revision = "mfa1a2b3c4d5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("audit_logs", sa.Column("chain_key", sa.String(length=255), nullable=True))
    op.create_index("ix_audit_logs_chain_key", "audit_logs", ["chain_key"])
    op.create_table(
        "audit_chain_heads",
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("organization_id", sa.String(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("chain_key", sa.String(length=255), nullable=False),
        sa.Column("head_hash", sa.String(length=64), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "chain_key", name="uq_audit_chain_heads_org_key"),
    )
    op.create_index("ix_audit_chain_heads_organization_id", "audit_chain_heads", ["organization_id"])

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE audit_chain_heads ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE audit_chain_heads FORCE ROW LEVEL SECURITY")
        op.execute(
            "CREATE POLICY acron_tenant_scope ON audit_chain_heads FOR ALL "
            "USING (current_setting('app.rls_bypass', true) = 'on' OR "
            "organization_id::text = nullif(current_setting('app.organization_id', true), '')) "
            "WITH CHECK (current_setting('app.rls_bypass', true) = 'on' OR "
            "organization_id::text = nullif(current_setting('app.organization_id', true), ''))"
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP POLICY IF EXISTS acron_tenant_scope ON audit_chain_heads")
        op.execute("ALTER TABLE audit_chain_heads NO FORCE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE audit_chain_heads DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_audit_chain_heads_organization_id", table_name="audit_chain_heads")
    op.drop_table("audit_chain_heads")
    op.drop_index("ix_audit_logs_chain_key", table_name="audit_logs")
    op.drop_column("audit_logs", "chain_key")
