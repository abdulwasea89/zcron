"""Record staff evidence before closing privacy erasure requests."""
from alembic import op
import sqlalchemy as sa

revision = 'j2e3f4g5h6i7'
down_revision = 'i1d2e3f4g5h6'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('data_subject_requests', sa.Column('review_checks', sa.JSON(), nullable=False, server_default='{}'))


def downgrade():
    op.drop_column('data_subject_requests', 'review_checks')
