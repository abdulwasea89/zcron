"""Persist dashboard attention preferences per staff membership."""

from alembic import op
import sqlalchemy as sa

revision = "y1z2a3b4c5d6"
down_revision = "x0y1z2a3b4c5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("organization_members", sa.Column(
        "dashboard_hidden_attention", sa.JSON(), nullable=False, server_default=sa.text("'[]'"),
    ))


def downgrade() -> None:
    with op.batch_alter_table("organization_members") as batch:
        batch.drop_column("dashboard_hidden_attention")
