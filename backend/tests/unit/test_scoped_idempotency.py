from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, func
from sqlmodel import Session, SQLModel, select

from app.models.audit_log import AuditLog
from app.models.idempotency_key import IdempotencyKey
from app.services import idempotency_service as requests


@contextmanager
def store():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    try:
        with Session(engine, autoflush=False) as db:
            class Facade:
                def get_bind(self):
                    return db.get_bind()

                async def execute(self, statement):
                    return db.execute(statement)

                def add(self, row):
                    db.add(row)

            yield db, Facade()
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_identical_keys_cannot_replay_another_gym_or_users_response():
    with store() as (db, session):
        for org, user in [("gym-a", "owner-a"), ("gym-b", "owner-a"), ("gym-a", "owner-b"), (None, None)]:
            claimed = await requests.claim(session, key="same-key", endpoint="cash.log", body={"amount": 20},
                                           organization_id=org, user_id=user)
            assert claimed.claimed is True
            await requests.complete(session, claimed.record, code=201, body=f"private:{org}:{user}")
            db.commit()
        replay = await requests.claim(session, key="same-key", endpoint="cash.log", body={"amount": 20},
                                       organization_id="gym-a", user_id="owner-a")
        assert replay.claimed is False and replay.cached_response == "private:gym-a:owner-a"
        assert db.exec(select(func.count()).select_from(IdempotencyKey)).one() == 4
        with pytest.raises(HTTPException) as error:
            await requests.claim(session, key="same-key", endpoint="cash.log", body={"amount": 21},
                                  organization_id="gym-a", user_id="owner-a")
        assert error.value.status_code == 422
        anonymous = await requests.claim(session, key="same-key", endpoint="cash.log", body={"amount": 20},
                                          organization_id="", user_id="")
        assert not anonymous.claimed and anonymous.cached_response == "private:None:None"


@pytest.mark.asyncio
@pytest.mark.parametrize("code,body,expected_code,expected_detail", [
    (402, '{"detail":"Payment failed."}', 402, "Payment failed."),
    (200, "invalid", 409, "The previous request failed. Review its status before retrying."),
])
async def test_failed_claim_never_replays_as_success(code, body, expected_code, expected_detail):
    with store() as (db, session):
        claim = await requests.claim(session, key="failed", endpoint="cash.log", body={"amount": 20},
                                     organization_id="gym", user_id="owner")
        await requests.fail(session, claim.record, code=code, body=body)
        db.commit()
        with pytest.raises(HTTPException) as error:
            await requests.claim(session, key="failed", endpoint="cash.log", body={"amount": 20},
                                 organization_id="gym", user_id="owner")
        assert (error.value.status_code, error.value.detail) == (expected_code, expected_detail)


def test_two_concurrent_requests_can_only_claim_once(tmp_path):
    import asyncio
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from sqlalchemy.sql import Select

    engine = create_engine(f"sqlite:///{tmp_path / 'claims.db'}", connect_args={"timeout": 10})
    SQLModel.metadata.create_all(engine)
    barrier = Barrier(2, timeout=10)

    def worker():
        async def run():
            with Session(engine, autoflush=False) as db:
                class RacingFacade:
                    checked = False

                    def get_bind(self):
                        return db.get_bind()

                    async def execute(self, statement):
                        result = db.execute(statement)
                        if isinstance(statement, Select) and not self.checked:
                            self.checked = True
                            barrier.wait()
                        return result

                    def add(self, row):
                        db.add(row)

                session = RacingFacade()
                result = await requests.claim(session, key="concurrent", endpoint="pay", body={},
                                               organization_id="gym", user_id="owner")
                if result.claimed:
                    await requests.complete(session, result.record, code=201, body="one result")
                db.commit()
                return result.claimed

        return asyncio.run(run())

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(worker) for _ in range(2)]
            assert sorted(future.result(timeout=20) for future in futures) == [False, True]
        with Session(engine) as db:
            assert db.exec(select(func.count()).select_from(IdempotencyKey)).one() == 1
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_stale_precheck_uses_atomic_claim_and_preserves_outer_transaction():
    with store() as (db, session):
        first = await requests.claim(session, key="race", endpoint="pay", body={}, organization_id="gym", user_id="owner")
        await requests.complete(session, first.record, code=201, body='{"payment_id":"original"}')
        db.commit()
        db.add(AuditLog(action="unrelated.pending_change", organization_id="gym"))
        db.flush()

        class StalePrecheck:
            checked = False

            def get_bind(self):
                return db.get_bind()

            async def execute(self, statement):
                if not self.checked:
                    self.checked = True
                    return SimpleNamespace(scalar_one_or_none=lambda: None)
                return db.execute(statement)

        replay = await requests.claim(StalePrecheck(), key="race", endpoint="pay", body={}, organization_id="gym", user_id="owner")
        assert not replay.claimed and replay.cached_response == '{"payment_id":"original"}'
        db.commit()
        assert db.exec(select(func.count()).select_from(IdempotencyKey)).one() == 1
        assert db.exec(select(AuditLog)).one().action == "unrelated.pending_change"


@pytest.mark.asyncio
async def test_failed_operation_can_roll_back_claim_for_a_clean_retry():
    with store() as (db, session):
        await requests.claim(session, key="rollback", endpoint="pay", body={})
        db.rollback()
        assert db.exec(select(IdempotencyKey)).all() == []
        assert (await requests.claim(session, key="rollback", endpoint="pay", body={})).claimed
        with pytest.raises(HTTPException) as error:
            await requests.claim(session, key="rollback", endpoint="pay", body={})
        assert error.value.status_code == 409


@pytest.mark.parametrize("upgrade", ["migration", "local_sqlite"])
def test_upgrade_preserves_duplicate_evidence_and_enforces_null_scope_uniqueness(monkeypatch, upgrade):
    from importlib import import_module

    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy.exc import IntegrityError

    from app.db.session import _upgrade_sqlite_late_migration_columns

    engine = create_engine("sqlite://")
    migration = import_module("app.db.migrations.versions.i1d2e3f4g5h6_scoped_idempotency")
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("CREATE TABLE idempotency_keys (id VARCHAR PRIMARY KEY, key VARCHAR NOT NULL, endpoint VARCHAR NOT NULL, organization_id VARCHAR, user_id VARCHAR, status VARCHAR NOT NULL, created_at DATETIME NOT NULL, response_body VARCHAR)")
            for identifier, org, user, status, body in [
                ("pending", "gym", "owner", "IN_PROGRESS", None),
                ("completed", "gym", "owner", "COMPLETED", "first payment evidence"),
                ("duplicate", "gym", "owner", "COMPLETED", "second payment evidence"),
                ("foreign", "other", "owner", "COMPLETED", "other gym evidence"),
                ("anonymous", None, None, "COMPLETED", "anonymous evidence"),
                ("empty-scope", "", "", "IN_PROGRESS", None),
            ]:
                connection.exec_driver_sql("INSERT INTO idempotency_keys VALUES (?, 'same', 'pay', ?, ?, ?, '2026-01-01', ?)",
                                           (identifier, org, user, status, body))
            if upgrade == "migration":
                monkeypatch.setattr(migration, "op", Operations(MigrationContext.configure(connection)))
                migration.upgrade()
            else:
                _upgrade_sqlite_late_migration_columns(connection)
                _upgrade_sqlite_late_migration_columns(connection)
            assert connection.exec_driver_sql("SELECT count(*) FROM idempotency_keys").scalar_one() == 6
            assert connection.exec_driver_sql("SELECT response_body FROM idempotency_keys WHERE id='duplicate'").scalar_one() == "second payment evidence"
            assert connection.exec_driver_sql("SELECT original_key FROM idempotency_keys WHERE id='pending'").scalar_one() == "same"
            with pytest.raises(IntegrityError):
                connection.exec_driver_sql("INSERT INTO idempotency_keys (id,key,endpoint,status,created_at) VALUES ('new','same','pay','IN_PROGRESS','2026-01-01')")
            if upgrade == "migration":
                migration.downgrade()
                assert connection.exec_driver_sql("SELECT count(*) FROM idempotency_keys WHERE key='same'").scalar_one() == 6
    finally:
        engine.dispose()
