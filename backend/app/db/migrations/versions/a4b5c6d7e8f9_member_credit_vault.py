"""Add auditable member vault credit and prepaid balance fields.

Revision ID: a4b5c6d7e8f9
Revises: a3e4f5a6b7c8
"""

from alembic import op
import sqlalchemy as sa

revision = "a4b5c6d7e8f9"
down_revision = "a3e4f5a6b7c8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("payments", sa.Column("vault_credited_minor", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("subscriptions", sa.Column("prepaid_value_minor", sa.Integer(), nullable=True))
    op.add_column("subscriptions", sa.Column("prepaid_value_at", sa.DateTime(), nullable=True))
    op.add_column("membership_change_requests", sa.Column("vault_credit_minor", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("membership_change_requests", sa.Column("prepaid_before_minor", sa.Integer(), nullable=True))
    op.create_table(
        "member_credit_accounts",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("organization_id", sa.String(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("member_id", sa.String(), sa.ForeignKey("organization_members.id"), nullable=False),
        sa.Column("currency", sa.String(), nullable=False),
        sa.Column("balance_minor", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("organization_id", "member_id", "currency", name="uq_member_credit_org_member_currency"),
    )
    op.create_index("ix_member_credit_accounts_organization_id", "member_credit_accounts", ["organization_id"])
    op.create_index("ix_member_credit_accounts_member_id", "member_credit_accounts", ["member_id"])
    op.create_table(
        "member_credit_entries",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("account_id", sa.String(), sa.ForeignKey("member_credit_accounts.id"), nullable=False),
        sa.Column("reference", sa.String(), nullable=False),
        sa.Column("amount_minor", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.UniqueConstraint("reference", name="uq_member_credit_entries_reference"),
    )
    op.create_index("ix_member_credit_entries_account_id", "member_credit_entries", ["account_id"])
    op.create_index("ix_member_credit_entries_reference", "member_credit_entries", ["reference"])


def downgrade() -> None:
    op.drop_index("ix_member_credit_entries_reference", table_name="member_credit_entries")
    op.drop_index("ix_member_credit_entries_account_id", table_name="member_credit_entries")
    op.drop_table("member_credit_entries")
    op.drop_index("ix_member_credit_accounts_member_id", table_name="member_credit_accounts")
    op.drop_index("ix_member_credit_accounts_organization_id", table_name="member_credit_accounts")
    op.drop_table("member_credit_accounts")
    op.drop_column("membership_change_requests", "prepaid_before_minor")
    op.drop_column("membership_change_requests", "vault_credit_minor")
    op.drop_column("subscriptions", "prepaid_value_at")
    op.drop_column("subscriptions", "prepaid_value_minor")
    op.drop_column("payments", "vault_credited_minor")
