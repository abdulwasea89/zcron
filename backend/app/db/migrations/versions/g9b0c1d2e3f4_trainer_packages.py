"""Add granted trainer session credits and log consumption."""

from alembic import op
import sqlalchemy as sa

revision = "g9b0c1d2e3f4"
down_revision = "f8a9b0c1d2e3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "trainer_packages",
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("organization_id", sa.String(), nullable=False),
        sa.Column("member_id", sa.String(), nullable=False),
        sa.Column("trainer_member_id", sa.String(), nullable=False),
        sa.Column("granted_by_user_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("total_sessions", sa.Integer(), nullable=False),
        sa.Column("used_sessions", sa.Integer(), nullable=False),
        sa.Column("granted_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint("total_sessions > 0", name="ck_trainer_package_total_positive"),
        sa.CheckConstraint("used_sessions >= 0 AND used_sessions <= total_sessions", name="ck_trainer_package_usage_range"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["member_id"], ["organization_members.id"]),
        sa.ForeignKeyConstraint(["trainer_member_id"], ["organization_members.id"]),
        sa.ForeignKeyConstraint(["granted_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("id", "organization_id", "member_id", "trainer_member_id"):
        op.create_index(f"ix_trainer_packages_{column}", "trainer_packages", [column])
    with op.batch_alter_table("trainer_session_logs") as batch:
        batch.add_column(sa.Column("package_id", sa.String(), nullable=True))
        batch.create_foreign_key("fk_trainer_session_logs_package_id", "trainer_packages", ["package_id"], ["id"])
        batch.create_index("ix_trainer_session_logs_package_id", ["package_id"])


def downgrade() -> None:
    with op.batch_alter_table("trainer_session_logs") as batch:
        batch.drop_index("ix_trainer_session_logs_package_id")
        batch.drop_constraint("fk_trainer_session_logs_package_id", type_="foreignkey")
        batch.drop_column("package_id")
    for column in ("id", "organization_id", "member_id", "trainer_member_id"):
        op.drop_index(f"ix_trainer_packages_{column}", table_name="trainer_packages")
    op.drop_table("trainer_packages")
