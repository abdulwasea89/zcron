"""Enable tenant-scoped PostgreSQL row-level security.

Revision ID: a6b7c8d9e0f1
Revises: q3r4s5t6u7v8
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "a6b7c8d9e0f1"
down_revision = "q3r4s5t6u7v8"
branch_labels = None
depends_on = None


def _tables_with_scope() -> list[tuple[str, set[str]]]:
    inspector = sa.inspect(op.get_bind())
    return [
        (table, {column["name"] for column in inspector.get_columns(table)})
        for table in inspector.get_table_names()
    ]


def _scope(columns: set[str], table: str) -> str:
    bypass = "current_setting('app.rls_bypass', true) = 'on'"
    organization = "organization_id::text = nullif(current_setting('app.organization_id', true), '')"
    clauses = [bypass]
    if "organization_id" in columns:
        clauses.append(organization)
    elif "user_id" in columns:
        clauses.append("user_id::text = nullif(current_setting('app.user_id', true), '')")
    if table == "organization_members":
        clauses.append("user_id::text = nullif(current_setting('app.user_id', true), '')")
    if table == "organizations":
        clauses.append("id::text = nullif(current_setting('app.organization_id', true), '')")
        clauses.append(
            "EXISTS (SELECT 1 FROM organization_members m "
            "WHERE m.organization_id = organizations.id "
            "AND m.user_id::text = nullif(current_setting('app.user_id', true), ''))"
        )
    if table == "users":
        clauses.append("id::text = nullif(current_setting('app.user_id', true), '')")
        clauses.append(
            "EXISTS (SELECT 1 FROM organization_members m "
            "WHERE m.user_id = users.id "
            "AND m.organization_id::text = nullif(current_setting('app.organization_id', true), ''))"
        )
    return " OR ".join(f"({clause})" for clause in clauses)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    quote = bind.dialect.identifier_preparer.quote
    for table, columns in _tables_with_scope():
        if "organization_id" not in columns and table not in {"users", "organizations"}:
            continue
        name = quote(table)
        policy = quote("acron_tenant_scope")
        expression = _scope(columns, table)
        op.execute(f"ALTER TABLE {name} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {name} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {policy} ON {name} FOR ALL "
            f"USING ({expression}) WITH CHECK ({expression})"
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    quote = bind.dialect.identifier_preparer.quote
    for table, columns in _tables_with_scope():
        if "organization_id" not in columns and table not in {"users", "organizations"}:
            continue
        name = quote(table)
        op.execute(f"DROP POLICY IF EXISTS {quote('acron_tenant_scope')} ON {name}")
        op.execute(f"ALTER TABLE {name} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {name} DISABLE ROW LEVEL SECURITY")
