"""Link retention cases to the existing staff task queue."""

from alembic import op
import sqlalchemy as sa

revision = "f8a9b0c1d2e3"
down_revision = "e7f8a9b0c1d2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("tasks") as batch:
        batch.add_column(sa.Column("category", sa.String(), nullable=False, server_default="general"))
        batch.add_column(sa.Column("related_member_id", sa.String(), nullable=True))
        batch.add_column(sa.Column("case_outcome", sa.String(), nullable=True))
        batch.create_foreign_key("fk_tasks_related_member", "organization_members", ["related_member_id"], ["id"])
        batch.create_index("ix_tasks_related_member_id", ["related_member_id"])
    op.create_index("uq_tasks_open_retention", "tasks", ["organization_id", "related_member_id"], unique=True,
                    sqlite_where=sa.text("category = 'retention' AND done = 0"),
                    postgresql_where=sa.text("category = 'retention' AND NOT done"))


def downgrade() -> None:
    op.drop_index("uq_tasks_open_retention", "tasks")
    with op.batch_alter_table("tasks") as batch:
        batch.drop_index("ix_tasks_related_member_id")
        batch.drop_constraint("fk_tasks_related_member", type_="foreignkey")
        batch.drop_column("case_outcome")
        batch.drop_column("related_member_id")
        batch.drop_column("category")
