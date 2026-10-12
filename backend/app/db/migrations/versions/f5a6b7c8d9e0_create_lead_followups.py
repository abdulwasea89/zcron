"""create day-based lead follow-up reminders

Revision ID: f5a6b7c8d9e0
Revises: e4f5a6b7c8d9
Create Date: 2026-10-12 00:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
import uuid

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = "f5a6b7c8d9e0"
down_revision: str | None = "e4f5a6b7c8d9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "lead_followups",
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("organization_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("lead_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("day", sa.Integer(), nullable=False),
        sa.Column("due_at", sa.DateTime(), nullable=False),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("completed_by", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("note", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.CheckConstraint("day IN (0, 1, 3, 7)", name="ck_lead_followup_day"),
        sa.CheckConstraint(
            "status IN ('scheduled', 'due', 'completed', 'skipped')",
            name="ck_lead_followup_status",
        ),
        sa.ForeignKeyConstraint(["completed_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("lead_id", "day", name="uq_lead_followup_day"),
    )
    with op.batch_alter_table("lead_followups", schema=None) as batch_op:
        batch_op.create_index("ix_lead_followups_id", ["id"], unique=False)
        batch_op.create_index("ix_lead_followups_organization_id", ["organization_id"], unique=False)
        batch_op.create_index("ix_lead_followups_lead_id", ["lead_id"], unique=False)
        batch_op.create_index("ix_lead_followups_day", ["day"], unique=False)
        batch_op.create_index("ix_lead_followups_due_at", ["due_at"], unique=False)
        batch_op.create_index("ix_lead_followups_status", ["status"], unique=False)

    leads = sa.table(
        "leads",
        sa.column("id", sa.String()),
        sa.column("organization_id", sa.String()),
        sa.column("stage", sa.String()),
    )
    followups = sa.table(
        "lead_followups",
        sa.column("created_at", sa.DateTime()),
        sa.column("updated_at", sa.DateTime()),
        sa.column("id", sa.String()),
        sa.column("organization_id", sa.String()),
        sa.column("lead_id", sa.String()),
        sa.column("day", sa.Integer()),
        sa.column("due_at", sa.DateTime()),
        sa.column("status", sa.String()),
    )
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    active_stages = {"new", "contacted", "trial_booked", "visited"}
    rows = op.get_bind().execute(sa.select(leads)).mappings()
    records = [
        {
            "created_at": now,
            "updated_at": now,
            "id": uuid.uuid4().hex,
            "organization_id": lead["organization_id"],
            "lead_id": lead["id"],
            "day": day,
            "due_at": now + timedelta(days=day),
            "status": "scheduled",
        }
        for lead in rows if lead["stage"] in active_stages
        for day in (0, 1, 3, 7)
    ]
    if records:
        op.get_bind().execute(followups.insert(), records)


def downgrade() -> None:
    op.drop_table("lead_followups")
