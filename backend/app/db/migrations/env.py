"""Alembic environment, wired to SQLModel metadata and async engine.

Reads the database URL from application settings so migrations target the same
database as the app. Supports both online (async) and offline modes.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy import pool
from sqlmodel import SQLModel

from app.core.config import settings
import app.db.base  # noqa: F401  registers all models

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=settings.is_sqlite,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=settings.is_sqlite,
    )
    with context.begin_transaction():
        if connection.dialect.name == "postgresql":
            connection.exec_driver_sql("SELECT set_config('app.rls_bypass', 'on', true)")
        context.run_migrations()


async def run_migrations_online() -> None:
    # Cloud Postgres defaults to TLS; ephemeral local Postgres can disable it.
    connect_args = {} if settings.is_sqlite else {"ssl": settings.database_ssl_mode}
    connectable = async_engine_from_config(
        {"sqlalchemy.url": settings.database_url},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args=connect_args,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
