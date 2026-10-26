"""Link independently billed household members without sharing entitlements."""
from alembic import op
import sqlalchemy as sa

revision = 'l4g5h6i7j8k9'
down_revision = 'k3f4g5h6i7j8'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('organization_members', sa.Column('family_billing_mode', sa.String(), nullable=False, server_default='shared_plan'))


def downgrade():
    if op.get_bind().execute(sa.text("SELECT 1 FROM organization_members WHERE family_billing_mode = 'independent' AND family_owner_member_id IS NOT NULL LIMIT 1")).first():
        raise RuntimeError('Unlink independently billed households before downgrading this migration.')
    op.drop_column('organization_members', 'family_billing_mode')
