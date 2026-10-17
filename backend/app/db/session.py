"""Async database engine and session management (SQLModel + SQLAlchemy async).

The engine is created from ``settings.database_url``. It works against both
async SQLite (local dev default) and async PostgreSQL (production) without code
changes. ``get_session`` is the FastAPI dependency that yields a transactional
``AsyncSession``.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

from app.core.config import settings

# SQLite needs check_same_thread disabled for async usage. Cloud Postgres
# (Neon/Supabase) requires TLS — asyncpg enables it via ssl="require".
if settings.is_sqlite:
    _connect_args: dict = {"check_same_thread": False}
else:
    _connect_args = {"ssl": "require"}

engine = create_async_engine(
    settings.database_url,
    echo=settings.db_echo,
    future=True,
    connect_args=_connect_args,
    # pool_pre_ping is harmless on sqlite and useful on postgres.
    pool_pre_ping=not settings.is_sqlite,
)

async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def init_db() -> None:
    """Create all tables. Used for local dev / tests when not using Alembic.

    Importing ``app.db.base`` guarantees every model is registered on
    ``SQLModel.metadata`` before ``create_all`` runs.
    """

    import app.db.base  # noqa: F401  (registers models)

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
        if settings.is_sqlite:
            # ``create_all`` creates new tables but does not evolve existing
            # ones. Local SQLite databases are often kept between app updates,
            # so add columns introduced to Lead since the database was created.
            # Production databases use Alembic migrations instead.
            await conn.run_sync(_upgrade_sqlite_leads_schema)
            await conn.run_sync(_upgrade_sqlite_member_profile_schema)
            await conn.run_sync(_upgrade_sqlite_plan_variants_schema)
            await conn.run_sync(_upgrade_sqlite_promotions_schema)
            await conn.run_sync(_upgrade_sqlite_freeze_schema)
            await conn.run_sync(_upgrade_sqlite_owner_onboarding_schema)
            await conn.run_sync(_upgrade_sqlite_credit_schema)
            await conn.run_sync(_upgrade_sqlite_membership_change_vault_schema)
            await conn.run_sync(_upgrade_sqlite_attendance_card_schema)
            await conn.run_sync(_upgrade_sqlite_inbox_delivery_schema)
            await conn.run_sync(_upgrade_sqlite_payment_method_schema)
            await conn.run_sync(_upgrade_sqlite_recurring_billing_schema)


def _upgrade_sqlite_owner_onboarding_schema(connection) -> None:
    """Keep existing local SQLite workspaces compatible with owner onboarding."""
    from sqlalchemy import inspect

    columns = {column["name"] for column in inspect(connection).get_columns("organizations")}
    additions = {
        "onboarding_complete": "BOOLEAN NOT NULL DEFAULT 1",
        "stripe_onboarding_session_id": "VARCHAR",
        "stripe_onboarding_attempt": "INTEGER NOT NULL DEFAULT 0",
    }
    for name, definition in additions.items():
        if name not in columns:
            connection.exec_driver_sql(
                f'ALTER TABLE organizations ADD COLUMN "{name}" {definition}'
            )


def _upgrade_sqlite_promotions_schema(connection) -> None:
    """Add item 12 columns to existing local databases; create_all makes the new table."""
    from sqlalchemy import inspect

    inspector = inspect(connection)
    for table, columns in {
        "membership_plans": {"joining_fee": "FLOAT NOT NULL DEFAULT 0"},
        "payments": {
            "plan_price_amount": "FLOAT", "joining_fee_amount": "FLOAT NOT NULL DEFAULT 0",
            "discount_amount": "FLOAT NOT NULL DEFAULT 0", "promo_code": "VARCHAR",
        },
    }.items():
        if table not in inspector.get_table_names():
            continue
        existing = {column["name"] for column in inspector.get_columns(table)}
        for name, sql_type in columns.items():
            if name not in existing:
                connection.exec_driver_sql(f'ALTER TABLE "{table}" ADD COLUMN "{name}" {sql_type}')


def _upgrade_sqlite_freeze_schema(connection) -> None:
    """Add freeze lifecycle metadata to existing local SQLite databases."""
    from sqlalchemy import inspect

    inspector = inspect(connection)
    for table, columns in {
        "organization_members": {"status_before_freeze": "VARCHAR"},
        "subscriptions": {"frozen_at": "DATETIME", "status_before_freeze": "VARCHAR"},
    }.items():
        if table not in inspector.get_table_names():
            continue
        existing = {column["name"] for column in inspector.get_columns(table)}
        for name, sql_type in columns.items():
            if name not in existing:
                connection.exec_driver_sql(f'ALTER TABLE "{table}" ADD COLUMN "{name}" {sql_type}')


def _upgrade_sqlite_leads_schema(connection) -> None:
    """Apply additive lead-column changes to existing local SQLite databases."""
    from sqlalchemy import inspect

    inspector = inspect(connection)
    if "leads" not in inspector.get_table_names():
        return

    existing = {column["name"] for column in inspector.get_columns("leads")}
    additions = {
        "converted_member_id": "VARCHAR",
        "referred_by_member_id": "VARCHAR",
        "email_followup_consent": "BOOLEAN NOT NULL DEFAULT 0",
        "email_followup_consent_at": "DATETIME",
        "lost_reason": "VARCHAR",
    }
    for name, definition in additions.items():
        if name not in existing:
            connection.exec_driver_sql(f'ALTER TABLE leads ADD COLUMN "{name}" {definition}')

    connection.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_leads_lost_reason ON leads (lost_reason)")


def _upgrade_sqlite_member_profile_schema(connection) -> None:
    """Keep existing local SQLite member rows readable without resetting data."""
    from sqlalchemy import inspect

    inspector = inspect(connection)
    if "organization_members" not in inspector.get_table_names():
        return
    existing = {column["name"] for column in inspector.get_columns("organization_members")}
    for name in ("goals", "health_notes", "id_document_type", "id_document_last4"):
        if name not in existing:
            connection.exec_driver_sql(
                f'ALTER TABLE organization_members ADD COLUMN "{name}" VARCHAR'
            )


def _upgrade_sqlite_plan_variants_schema(connection) -> None:
    """Apply additive plan columns to existing local SQLite databases."""
    from sqlalchemy import inspect

    inspector = inspect(connection)
    tables = set(inspector.get_table_names())
    additions = {
        "membership_plans": {
            "audience": "VARCHAR NOT NULL DEFAULT 'standard'",
            "family_capacity": "INTEGER",
            "off_peak_start": "VARCHAR",
            "off_peak_end": "VARCHAR",
            "included_credits": "INTEGER",
        },
        "organization_members": {"family_owner_member_id": "VARCHAR"},
        "subscriptions": {"credits_allowance": "INTEGER"},
        "attendance": {"credit_subscription_id": "VARCHAR"},
    }
    for table, columns in additions.items():
        if table not in tables:
            continue
        existing = {column["name"] for column in inspector.get_columns(table)}
        for name, sql_type in columns.items():
            if name not in existing:
                connection.exec_driver_sql(f'ALTER TABLE "{table}" ADD COLUMN "{name}" {sql_type}')
    if "organization_members" in tables:
        connection.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_organization_members_family_owner_member_id "
            "ON organization_members (family_owner_member_id)"
        )


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yield a session, commit on success, rollback on error."""

    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def _upgrade_sqlite_credit_schema(connection) -> None:
    from sqlalchemy import inspect
    inspector = inspect(connection)
    for table, fields in {
        "subscriptions": {"prepaid_value_minor": "INTEGER", "prepaid_value_at": "DATETIME"},
        "payments": {"vault_credited_minor": "INTEGER NOT NULL DEFAULT 0"},
    }.items():
        existing = {c["name"] for c in inspector.get_columns(table)}
        for name, kind in fields.items():
            if name not in existing:
                connection.exec_driver_sql(f'ALTER TABLE "{table}" ADD COLUMN "{name}" {kind}')


def _upgrade_sqlite_membership_change_vault_schema(connection) -> None:
    from sqlalchemy import inspect
    if "membership_change_requests" not in inspect(connection).get_table_names():
        return
    columns = {c["name"] for c in inspect(connection).get_columns("membership_change_requests")}
    for name, kind in {"vault_credit_minor": "INTEGER NOT NULL DEFAULT 0", "prepaid_before_minor": "INTEGER"}.items():
        if name not in columns:
            connection.exec_driver_sql(f'ALTER TABLE membership_change_requests ADD COLUMN "{name}" {kind}')


def _upgrade_sqlite_attendance_card_schema(connection) -> None:
    """Add local-dev RFID assignment support to existing SQLite workspaces."""
    from sqlalchemy import inspect

    inspector = inspect(connection)
    if "organization_members" not in inspector.get_table_names():
        return
    columns = {c["name"] for c in inspector.get_columns("organization_members")}
    if "attendance_card_uid" not in columns:
        connection.exec_driver_sql(
            'ALTER TABLE organization_members ADD COLUMN "attendance_card_uid" VARCHAR'
        )
    connection.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_organization_members_attendance_card_uid "
        "ON organization_members (attendance_card_uid)"
    )
    connection.exec_driver_sql(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_org_member_attendance_card_uid "
        "ON organization_members (organization_id, attendance_card_uid)"
    )


def _upgrade_sqlite_inbox_delivery_schema(connection) -> None:
    """Add delivery error details to existing local inbox databases."""
    from sqlalchemy import inspect

    inspector = inspect(connection)
    if "inbox_messages" not in inspector.get_table_names():
        return
    columns = {c["name"] for c in inspector.get_columns("inbox_messages")}
    if "delivery_error" not in columns:
        connection.exec_driver_sql("ALTER TABLE inbox_messages ADD COLUMN delivery_error VARCHAR")
        connection.exec_driver_sql(
            "UPDATE inbox_messages SET delivery_status = 'unknown' "
            "WHERE direction = 'outbound' AND delivery_status = 'sent'"
        )


def _upgrade_sqlite_payment_method_schema(connection) -> None:
    """Add actual Stripe method labels to existing local payment ledgers."""
    from sqlalchemy import inspect

    inspector = inspect(connection)
    if "payments" not in inspector.get_table_names():
        return
    columns = {c["name"] for c in inspector.get_columns("payments")}
    if "stripe_payment_method_type" not in columns:
        connection.exec_driver_sql(
            'ALTER TABLE payments ADD COLUMN "stripe_payment_method_type" VARCHAR(48)'
        )


def _upgrade_sqlite_recurring_billing_schema(connection) -> None:
    """Add web recurring billing consent and saved Stripe references locally."""
    from sqlalchemy import inspect

    inspector = inspect(connection)
    additions = {
        "organization_members": {
            "stripe_customer_id": "VARCHAR",
            "stripe_default_payment_method_id": "VARCHAR",
            "stripe_default_payment_method_type": "VARCHAR(48)",
            "recurring_consent_at": "DATETIME",
            "stripe_recurring_setup_intent_id": "VARCHAR",
        },
        "subscriptions": {
            "auto_renew": "BOOLEAN NOT NULL DEFAULT 0",
            "renewal_attempt_count": "INTEGER NOT NULL DEFAULT 0",
            "next_renewal_attempt_at": "DATETIME",
        },
        "payments": {
            "recurring_consent": "BOOLEAN NOT NULL DEFAULT 0",
            "stripe_payment_method_id": "VARCHAR",
        },
    }
    for table, columns in additions.items():
        existing = {column["name"] for column in inspector.get_columns(table)}
        for name, definition in columns.items():
            if name not in existing:
                connection.exec_driver_sql(
                    f'ALTER TABLE "{table}" ADD COLUMN "{name}" {definition}'
                )
