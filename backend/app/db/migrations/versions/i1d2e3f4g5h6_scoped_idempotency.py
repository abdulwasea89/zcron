"""Uniquely claim requests within their workspace and user scope."""

from alembic import op
import sqlalchemy as sa

revision = "i1d2e3f4g5h6"
down_revision = "h0c1d2e3f4g5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("idempotency_keys", sa.Column("original_key", sa.String(), nullable=True))
    connection = op.get_bind()
    connection.exec_driver_sql("UPDATE idempotency_keys SET organization_id=NULL WHERE organization_id=''")
    connection.exec_driver_sql("UPDATE idempotency_keys SET user_id=NULL WHERE user_id=''")
    duplicates = connection.execute(sa.text("""
        SELECT id, key FROM (
            SELECT id, key, ROW_NUMBER() OVER (
                PARTITION BY key, endpoint, coalesce(organization_id, ''), coalesce(user_id, '')
                ORDER BY CASE WHEN lower(cast(status AS TEXT)) = 'completed' THEN 0 ELSE 1 END,
                         created_at, id
            ) AS position FROM idempotency_keys
        ) AS ranked WHERE position > 1
    """)).all()
    # Preserve duplicate records and their original keys rather than deleting request evidence.
    for row in duplicates:
        connection.execute(sa.text("UPDATE idempotency_keys SET original_key=:original, key=:archived WHERE id=:id"),
                           {"id": row.id, "original": row.key, "archived": f"archived-duplicate:{row.id}"})
    op.create_index("uq_idempotency_scope_key", "idempotency_keys", [
        "key", "endpoint", sa.text("coalesce(organization_id, '')"), sa.text("coalesce(user_id, '')"),
    ], unique=True)


def downgrade() -> None:
    op.drop_index("uq_idempotency_scope_key", table_name="idempotency_keys")
    op.execute("UPDATE idempotency_keys SET key=original_key WHERE original_key IS NOT NULL")
    with op.batch_alter_table("idempotency_keys") as batch:
        batch.drop_column("original_key")
