"""Record the first time a lead reaches Contacted.

Revision ID: r3s4t5u6v7w8
Revises: q2r3s4t5u6v7
"""

from __future__ import annotations

import json

from alembic import op
import sqlalchemy as sa


revision = "r3s4t5u6v7w8"
down_revision = "q2r3s4t5u6v7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("leads", sa.Column("first_contacted_at", sa.DateTime(), nullable=True))
    connection = op.get_bind()
    events = connection.execute(sa.text(
        "SELECT entity_id, created_at, new_values_json FROM audit_logs "
        "WHERE action = 'lead.stage_changed' AND entity_type = 'lead' "
        "ORDER BY created_at ASC"
    )).all()
    for lead_id, created_at, values in events:
        try:
            contacted = json.loads(values or "{}").get("stage") in {"contacted", "trial_booked", "visited", "joined"}
        except (TypeError, ValueError):
            contacted = False
        if contacted:
            connection.execute(sa.text(
                "UPDATE leads SET first_contacted_at = :created_at "
                "WHERE id = :lead_id AND first_contacted_at IS NULL"
            ), {"created_at": created_at, "lead_id": lead_id})


def downgrade() -> None:
    op.drop_column("leads", "first_contacted_at")
