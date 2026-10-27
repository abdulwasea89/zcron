"""Run with TEST_POSTGRES_URL against an isolated PostgreSQL test database."""

import asyncio
from importlib import import_module
import os
import uuid
from unittest.mock import AsyncMock

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel, select

import app.db.base  # noqa: F401
from app.core.constants import ReceiptStatus
from app.models.membership import OrganizationMember
from app.models.organization import Organization
from app.models.payment import Payment
from app.models.plan import MembershipPlan
from app.models.receipt import ReceiptUpload
from app.models.user import User
from app.services import audit_service, family_service, receipts_service, referrals_service


@pytest.mark.skipif(not os.environ.get("TEST_POSTGRES_URL"), reason="TEST_POSTGRES_URL is not configured")
async def test_concurrent_receipt_approvals_create_one_payment(monkeypatch):
    url = os.environ["TEST_POSTGRES_URL"]
    schema = f"receipt_test_{uuid.uuid4().hex}"
    admin = create_async_engine(url)
    async with admin.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(url, connect_args={"server_settings": {"search_path": schema}})
    locked = asyncio.Event()
    release = asyncio.Event()

    async def hold_first_review(*_args, **_kwargs):
        locked.set()
        await release.wait()

    monkeypatch.setattr(receipts_service, "_notify", hold_first_review)
    monkeypatch.setattr(receipts_service.events, "receipt_processed", AsyncMock())
    monkeypatch.setattr(audit_service, "record_audit", AsyncMock())
    monkeypatch.setattr(family_service, "sync_family_status", AsyncMock())
    monkeypatch.setattr(referrals_service, "qualify_referral_for_member", AsyncMock())
    try:
        async with engine.begin() as connection:
            await connection.run_sync(SQLModel.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions.begin() as session:
            session.add_all([
                Organization(id="gym", name="Gym", org_code="GYM"),
                User(id="user", email="receipt@example.test", hashed_password="unused"),
                User(id="staff", email="staff@example.test", hashed_password="unused"),
            ])
            await session.flush()
            session.add_all([
                OrganizationMember(id="member", organization_id="gym", user_id="user"),
                MembershipPlan(id="plan", organization_id="gym", name="Plan", price=100),
            ])
            await session.flush()
            session.add(ReceiptUpload(id="receipt", organization_id="gym", member_id="member", plan_id="plan",
                                      status=ReceiptStatus.PENDING_REVIEW))

        async def approve():
            async with sessions.begin() as session:
                try:
                    await receipts_service.review(session, org_id="gym", receipt_id="receipt", action="approve",
                        reason=None, reviewer_user_id="staff", settlement_confirmed=True, verified_amount=100)
                    return "approved"
                except HTTPException as exc:
                    return exc.status_code

        first = asyncio.create_task(approve())
        await asyncio.wait_for(locked.wait(), timeout=5)
        second = asyncio.create_task(approve())
        await asyncio.sleep(0.2)
        assert not second.done()
        release.set()
        assert await asyncio.wait_for(asyncio.gather(first, second), timeout=5) == ["approved", 409]
        async with sessions() as session:
            payments = (await session.execute(select(Payment).where(Payment.receipt_id == "receipt"))).scalars().all()
            assert len(payments) == 1
    finally:
        release.set()
        await engine.dispose()
        async with admin.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.dispose()


@pytest.mark.skipif(not os.environ.get("TEST_POSTGRES_URL"), reason="TEST_POSTGRES_URL is not configured")
async def test_cash_reconciliation_migration_preserves_postgres_rows(monkeypatch):
    schema = f"cash_test_{uuid.uuid4().hex}"
    engine = create_async_engine(os.environ["TEST_POSTGRES_URL"])
    migration = import_module("app.db.migrations.versions.c2d3e4f5a6b7_cash_reconciliation_currency")
    try:
        async with engine.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            await connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            await connection.execute(text("CREATE TABLE cash_reconciliations (id VARCHAR PRIMARY KEY, system_total FLOAT)"))
            await connection.execute(text("INSERT INTO cash_reconciliations VALUES ('old', 42)"))

            def migrate(sync_connection):
                monkeypatch.setattr(migration, "op", Operations(MigrationContext.configure(sync_connection)))
                migration.upgrade()

            await connection.run_sync(migrate)
            row = (await connection.execute(text("SELECT system_total, currency, opening_float FROM cash_reconciliations"))).one()
            assert tuple(row) == (42, None, 0)
    finally:
        async with engine.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await engine.dispose()
