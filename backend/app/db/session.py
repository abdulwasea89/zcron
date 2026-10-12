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


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yield a session, commit on success, rollback on error."""

    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
