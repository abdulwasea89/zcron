"""Store reusable tenant-scoped member tags."""

from alembic import op
import sqlalchemy as sa

revision = "z2a3b4c5d6e7"
down_revision = "y1z2a3b4c5d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("organization_members", sa.Column("tags", sa.JSON(), nullable=False, server_default=sa.text("'[]'")))


def downgrade() -> None:
    with op.batch_alter_table("organization_members") as batch:
        batch.drop_column("tags")
