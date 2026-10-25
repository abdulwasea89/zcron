"""Add recurring trainer availability windows."""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = "v8w9x0y1z2a3"
down_revision: str | None = "u7v8w9x0y1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "trainer_availability",
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("organization_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("trainer_member_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("weekday", sa.Integer(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.CheckConstraint("weekday BETWEEN 0 AND 6", name="ck_trainer_availability_weekday"),
        sa.CheckConstraint("start_time < end_time", name="ck_trainer_availability_time_range"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["trainer_member_id"], ["organization_members.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id", "trainer_member_id", "weekday", "start_time", "end_time",
            name="uq_trainer_availability_window",
        ),
    )
    with op.batch_alter_table("trainer_availability", schema=None) as batch_op:
        batch_op.create_index("ix_trainer_availability_id", ["id"], unique=False)
        batch_op.create_index("ix_trainer_availability_organization_id", ["organization_id"], unique=False)
        batch_op.create_index("ix_trainer_availability_trainer_member_id", ["trainer_member_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("trainer_availability", schema=None) as batch_op:
        batch_op.drop_index("ix_trainer_availability_trainer_member_id")
        batch_op.drop_index("ix_trainer_availability_organization_id")
        batch_op.drop_index("ix_trainer_availability_id")
    op.drop_table("trainer_availability")
