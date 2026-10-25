"""Separate WhatsApp consent and approved campaign templates."""

from alembic import op
import sqlalchemy as sa

revision = "d6e7f8a9b0c1"
down_revision = "c5d6e7f8a9b0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    if connection.dialect.name == "postgresql":
        # Older migrations used VARCHAR; metadata-created databases may use an enum.
        exists = connection.execute(sa.text("SELECT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'campaignchannel')")).scalar()
        if exists:
            with op.get_context().autocommit_block():
                op.execute("ALTER TYPE campaignchannel ADD VALUE IF NOT EXISTS 'WHATSAPP'")
    op.add_column("organization_members", sa.Column("marketing_whatsapp_consent", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("organization_members", sa.Column("marketing_whatsapp_consent_at", sa.DateTime(), nullable=True))
    op.add_column("campaigns", sa.Column("whatsapp_template_sid", sa.String(), nullable=True))
    op.add_column("campaigns", sa.Column("whatsapp_variables", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))
    op.add_column("campaigns", sa.Column("member_tag", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("campaigns") as batch:
        batch.drop_column("member_tag")
        batch.drop_column("whatsapp_variables")
        batch.drop_column("whatsapp_template_sid")
    with op.batch_alter_table("organization_members") as batch:
        batch.drop_column("marketing_whatsapp_consent_at")
        batch.drop_column("marketing_whatsapp_consent")
