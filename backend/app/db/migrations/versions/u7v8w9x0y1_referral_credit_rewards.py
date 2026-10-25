"""Configure and snapshot referral credit amounts.

Revision ID: u7v8w9x0y1
Revises: t6u7v8w9x0
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "u7v8w9x0y1"
down_revision: str | None = "t6u7v8w9x0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "referral_programs",
        sa.Column("reward_amount_minor", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "referral_programs",
        sa.Column("reward_currency", sa.String(), nullable=False, server_default="USD"),
    )
    op.add_column(
        "referral_rewards",
        sa.Column("amount_minor", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "referral_rewards",
        sa.Column("currency", sa.String(), nullable=False, server_default="USD"),
    )


def downgrade() -> None:
    op.drop_column("referral_rewards", "currency")
    op.drop_column("referral_rewards", "amount_minor")
    op.drop_column("referral_programs", "reward_currency")
    op.drop_column("referral_programs", "reward_amount_minor")
