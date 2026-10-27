"""Pytest fixtures: isolated in-memory DB + ASGI test client.

Each test runs against a fresh SQLite schema so tests don't share state. The
app's ``get_session`` dependency is overridden to use the test engine.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

import app.db.base  # noqa: F401  registers models
from app.api.deps import get_session
from app.main import app


@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        hide_parameters=True,
    )
    async with eng.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_maker(engine):
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False, autoflush=False)


@pytest_asyncio.fixture
async def client(session_maker):
    async def _override_get_session():
        async with session_maker() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise

    app.dependency_overrides[get_session] = _override_get_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def db(session_maker):
    """Direct DB session for test setup/inspection."""

    async with session_maker() as s:
        yield s


@pytest.fixture(autouse=True)
def reset_process_globals():
    """Reset process-local state shared across tests.

    The in-memory rate limiter and the email/push dev outboxes are module-level
    singletons. Without resetting them, per-email/per-IP signup and resend limits
    (and stale verification emails) leak between tests and cause false failures.
    """

    from app.core.config import settings
    from app.core.rate_limit import rate_limiter
    from app.integrations import email as email_mod
    from app.integrations import push as push_mod
    from app.integrations.stripe_client import platform_stripe
    from app.integrations.stripe_connect import connect_stripe

    # Force email stub mode so tests never hit a real provider (the dev .env may
    # carry a live Resend key or SMTP creds). Stub mode captures every email in
    # `outbox`, which the helpers read for verification codes.
    saved_key = settings.resend_api_key
    saved_smtp_host = settings.smtp_host
    saved_stripe_key = settings.stripe_secret_key
    saved_platform_live = platform_stripe.live
    saved_connect_live = connect_stripe.live
    saved_hibp = settings.hibp_enabled
    settings.resend_api_key = None
    settings.smtp_host = ""
    settings.stripe_secret_key = ""
    platform_stripe.live = False
    connect_stripe.live = False
    settings.hibp_enabled = False

    rate_limiter._memory._events.clear()
    email_mod.outbox.clear()
    push_mod.outbox.clear()
    yield
    settings.resend_api_key = saved_key
    settings.smtp_host = saved_smtp_host
    settings.stripe_secret_key = saved_stripe_key
    platform_stripe.live = saved_platform_live
    connect_stripe.live = saved_connect_live
    settings.hibp_enabled = saved_hibp
