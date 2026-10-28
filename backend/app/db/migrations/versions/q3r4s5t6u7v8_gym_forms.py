"""Add versioned gym forms and staff-collected signed evidence."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
import sqlmodel

revision: str = "q3r4s5t6u7v8"
down_revision: str | None = "p1q2r3s4t5u6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "gym_forms",
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("organization_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("form_key", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("title", sqlmodel.sql.sqltypes.AutoString(length=160), nullable=False),
        sa.Column("form_type", sqlmodel.sql.sqltypes.AutoString(length=24), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("body", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_by", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "form_key", "version", name="uq_gym_form_version"),
    )
    for column in ("id", "organization_id", "form_key", "form_type", "active"):
        op.create_index(f"ix_gym_forms_{column}", "gym_forms", [column])

    op.create_table(
        "gym_form_acceptances",
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("organization_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("member_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("form_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("form_title", sqlmodel.sql.sqltypes.AutoString(length=160), nullable=False),
        sa.Column("form_type", sqlmodel.sql.sqltypes.AutoString(length=24), nullable=False),
        sa.Column("form_version", sa.Integer(), nullable=False),
        sa.Column("form_body_snapshot", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("signed_by_name", sqlmodel.sql.sqltypes.AutoString(length=160), nullable=False),
        sa.Column("recorded_at", sa.DateTime(), nullable=False),
        sa.Column("collected_by", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("evidence_data", sa.LargeBinary(), nullable=False),
        sa.Column("evidence_media_type", sqlmodel.sql.sqltypes.AutoString(length=32), nullable=False),
        sa.Column("evidence_filename", sqlmodel.sql.sqltypes.AutoString(length=180), nullable=False),
        sa.Column("evidence_sha256", sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["member_id"], ["organization_members.id"]),
        sa.ForeignKeyConstraint(["form_id"], ["gym_forms.id"]),
        sa.ForeignKeyConstraint(["collected_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "member_id", "form_id", name="uq_gym_form_acceptance_member_version"),
    )
    for column in ("id", "organization_id", "member_id", "form_id", "recorded_at", "evidence_sha256"):
        op.create_index(f"ix_gym_form_acceptances_{column}", "gym_form_acceptances", [column])


def downgrade() -> None:
    for column in ("id", "organization_id", "member_id", "form_id", "recorded_at", "evidence_sha256"):
        op.drop_index(f"ix_gym_form_acceptances_{column}", table_name="gym_form_acceptances")
    op.drop_table("gym_form_acceptances")
    for column in ("id", "organization_id", "form_key", "form_type", "active"):
        op.drop_index(f"ix_gym_forms_{column}", table_name="gym_forms")
    op.drop_table("gym_forms")
