"""Add organization-scoped RFID card identifiers for web check-in.

Revision ID: b7c8d9e0f1a2
Revises: a4b5c6d7e8f9
"""

from alembic import op
import sqlalchemy as sa


revision = "b7c8d9e0f1a2"
down_revision = "a4b5c6d7e8f9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("organization_members") as batch:
        batch.add_column(sa.Column("attendance_card_uid", sa.String(), nullable=True))
        batch.create_index("ix_organization_members_attendance_card_uid", ["attendance_card_uid"])
        batch.create_unique_constraint(
            "uq_org_member_attendance_card_uid",
            ["organization_id", "attendance_card_uid"],
        )


def downgrade() -> None:
    with op.batch_alter_table("organization_members") as batch:
        batch.drop_constraint("uq_org_member_attendance_card_uid", type_="unique")
        batch.drop_index("ix_organization_members_attendance_card_uid")
        batch.drop_column("attendance_card_uid")
