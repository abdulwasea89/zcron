"""Track booked-member operational class reminders."""

from alembic import op
import sqlalchemy as sa

revision = "b4c5d6e7f8a9"
down_revision = "a3b4c5d6e7f8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("class_bookings", sa.Column("reminder_created_at", sa.DateTime(), nullable=True))
    op.add_column("class_bookings", sa.Column("reminder_email_accepted", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    with op.batch_alter_table("class_bookings") as batch:
        batch.drop_column("reminder_email_accepted")
        batch.drop_column("reminder_created_at")
