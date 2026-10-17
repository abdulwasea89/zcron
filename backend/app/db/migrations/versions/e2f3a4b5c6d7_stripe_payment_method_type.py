"""Record the actual Stripe payment method selected in Payment Element.

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
"""

from alembic import op
import sqlalchemy as sa

revision = "e2f3a4b5c6d7"
down_revision = "d1e2f3a4b5c6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("payments", sa.Column("stripe_payment_method_type", sa.String(length=48), nullable=True))


def downgrade() -> None:
    op.drop_column("payments", "stripe_payment_method_type")
