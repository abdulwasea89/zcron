"""Preserve whether tax was included in a payment's quoted price."""
from alembic import op
import sqlalchemy as sa

revision = 'k3f4g5h6i7j8'
down_revision = 'j2e3f4g5h6i7'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('payments', sa.Column('tax_included', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    op.drop_column('payments', 'tax_included')
