"""Attribute first lead contact to the staff member who advanced it.

Revision ID: r4s5t6u7v8w9
Revises: r3s4t5u6v7w8
"""

from __future__ import annotations

import json

from alembic import op
import sqlalchemy as sa


revision = "r4s5t6u7v8w9"
down_revision = "r3s4t5u6v7w8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("leads") as batch:
        batch.add_column(sa.Column(
            "first_contacted_by_user_id", sa.String(), sa.ForeignKey("users.id"), nullable=True,
        ))

    connection = op.get_bind()
    events = connection.execute(sa.text(
        "SELECT entity_id, actor_user_id, new_values_json FROM audit_logs "
        "WHERE action = 'lead.stage_changed' AND entity_type = 'lead' "
        "ORDER BY created_at ASC"
    )).all()
    for lead_id, actor_user_id, values in events:
        try:
            contacted = json.loads(values or "{}").get("stage") in {
                "contacted", "trial_booked", "visited", "joined",
            }
        except (TypeError, ValueError):
            contacted = False
        if contacted and actor_user_id:
            connection.execute(sa.text(
                "UPDATE leads SET first_contacted_by_user_id = :actor_user_id "
                "WHERE id = :lead_id AND first_contacted_at IS NOT NULL "
                "AND first_contacted_by_user_id IS NULL "
                "AND EXISTS (SELECT 1 FROM users WHERE users.id = :actor_user_id)"
            ), {"actor_user_id": actor_user_id, "lead_id": lead_id})


def downgrade() -> None:
    with op.batch_alter_table("leads") as batch:
        batch.drop_column("first_contacted_by_user_id")
