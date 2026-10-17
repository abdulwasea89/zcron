"""Persist member consent and Stripe Connect off-session renewal references.

Revision ID: f3a4b5c6d7e8
Revises: e2f3a4b5c6d7
"""

from alembic import op
import sqlalchemy as sa

revision = "f3a4b5c6d7e8"
down_revision = "e2f3a4b5c6d7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("organization_members", sa.Column("stripe_customer_id", sa.String(), nullable=True))
    op.add_column("organization_members", sa.Column("stripe_default_payment_method_id", sa.String(), nullable=True))
    op.add_column("organization_members", sa.Column("stripe_default_payment_method_type", sa.String(length=48), nullable=True))
    op.add_column("organization_members", sa.Column("recurring_consent_at", sa.DateTime(), nullable=True))
    op.add_column("organization_members", sa.Column("stripe_recurring_setup_intent_id", sa.String(), nullable=True))
    op.create_index("ix_organization_members_stripe_customer_id", "organization_members", ["stripe_customer_id"])
    op.add_column("subscriptions", sa.Column("auto_renew", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("subscriptions", sa.Column("renewal_attempt_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("subscriptions", sa.Column("next_renewal_attempt_at", sa.DateTime(), nullable=True))
    op.add_column("payments", sa.Column("recurring_consent", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("payments", sa.Column("stripe_payment_method_id", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("payments", "stripe_payment_method_id")
    op.drop_column("payments", "recurring_consent")
    op.drop_column("subscriptions", "next_renewal_attempt_at")
    op.drop_column("subscriptions", "renewal_attempt_count")
    op.drop_column("subscriptions", "auto_renew")
    op.drop_index("ix_organization_members_stripe_customer_id", table_name="organization_members")
    op.drop_column("organization_members", "recurring_consent_at")
    op.drop_column("organization_members", "stripe_recurring_setup_intent_id")
    op.drop_column("organization_members", "stripe_default_payment_method_id")
    op.drop_column("organization_members", "stripe_default_payment_method_type")
    op.drop_column("organization_members", "stripe_customer_id")
