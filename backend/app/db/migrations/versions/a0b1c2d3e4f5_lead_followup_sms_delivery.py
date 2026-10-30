"""Record consented SMS lead follow-up delivery attempts."""

from alembic import op
import sqlalchemy as sa

revision = "a0b1c2d3e4f5"
down_revision = "f9a0b1c2d3e4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("lead_followups", sa.Column("sms_status", sa.String(), nullable=False, server_default="pending"))
    op.add_column("lead_followups", sa.Column("sms_attempted_at", sa.DateTime(), nullable=True))
    op.add_column("lead_followups", sa.Column("sms_sent_at", sa.DateTime(), nullable=True))
    op.add_column("lead_followups", sa.Column("sms_attempts", sa.Integer(), nullable=False, server_default="0"))
    op.create_index("ix_lead_followups_sms_status", "lead_followups", ["sms_status"])
    with op.batch_alter_table("lead_followups") as batch_op:
        batch_op.create_check_constraint(
            "ck_lead_followup_sms_status",
            "sms_status IN ('pending', 'sent', 'failed', 'skipped')",
        )
    with op.batch_alter_table("lead_followups") as batch:
        batch.alter_column("sms_status", server_default=None)
    with op.batch_alter_table("lead_followups") as batch:
        batch.alter_column("sms_attempts", server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("lead_followups") as batch_op:
        batch_op.drop_constraint("ck_lead_followup_sms_status", type_="check")
    op.drop_index("ix_lead_followups_sms_status", table_name="lead_followups")
    op.drop_column("lead_followups", "sms_attempts")
    op.drop_column("lead_followups", "sms_sent_at")
    op.drop_column("lead_followups", "sms_attempted_at")
    op.drop_column("lead_followups", "sms_status")
