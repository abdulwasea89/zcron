from datetime import timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.core.security import now_utc
from app.models.trainer_package import TrainerPackage
from app.services import trainer_packages_service as packages


@pytest.mark.asyncio
async def test_consume_package_decrements_credit_and_audits(monkeypatch):
    package = TrainerPackage(id="bundle", organization_id="gym", member_id="member",
                             trainer_member_id="trainer", granted_by_user_id="owner",
                             name="Ten sessions", total_sessions=10, used_sessions=3)
    session = SimpleNamespace(get=lambda *_args, **_kwargs: None, add=lambda _row: None)

    async def get(*_args, **_kwargs):
        return package

    session.get = get
    audits = []

    async def audit(_session, **data):
        audits.append(data)

    monkeypatch.setattr(packages, "record_audit", audit)
    result = await packages.consume_package(session, org_id="gym", package_id="bundle",
                                            trainer_member_id="trainer", member_id="member")
    assert result.used_sessions == 4
    assert audits[0]["metadata"]["remaining"] == 6


@pytest.mark.asyncio
@pytest.mark.parametrize("changes", [
    {"organization_id": "other"},
    {"trainer_member_id": "other-trainer"},
    {"member_id": "other-member"},
    {"used_sessions": 1},
    {"expires_at": now_utc() - timedelta(seconds=1)},
    {"cancelled_at": now_utc()},
])
async def test_consume_rejects_wrong_or_unusable_package(monkeypatch, changes):
    values = dict(id="bundle", organization_id="gym", member_id="member",
                  trainer_member_id="trainer", granted_by_user_id="owner",
                  name="One session", total_sessions=1, used_sessions=0)
    values.update(changes)
    package = TrainerPackage(**values)
    session = SimpleNamespace(get=lambda *_args, **_kwargs: None, add=lambda _row: None)

    async def get(*_args, **_kwargs):
        return package

    session.get = get
    with pytest.raises(HTTPException):
        await packages.consume_package(session, org_id="gym", package_id="bundle",
                                       trainer_member_id="trainer", member_id="member")


@pytest.mark.asyncio
async def test_package_session_retry_returns_cached_log_without_consuming(monkeypatch):
    from app.api.v1.routes import staff
    from app.core.constants import Role
    from app.schemas.staff import TrainerSessionCreate, TrainerSessionOut

    cached = TrainerSessionOut(id="saved", client_member_id="member", client_name="Member",
                               performed_at=now_utc(), duration_minutes=45, focus="Strength", notes="",
                               package_id="bundle")

    async def claim(*_args, **kwargs):
        assert kwargs["endpoint"] == "trainer.package_session:gym:trainer-user"
        return SimpleNamespace(claimed=False, cached_response=cached.model_dump_json())

    async def unexpected(*_args, **_kwargs):
        raise AssertionError("A replay must not create another session or consume another credit")

    monkeypatch.setattr(staff.idempotency_service, "claim", claim)
    monkeypatch.setattr(staff.trainer_sessions, "create_log", unexpected)
    result = await staff.create_trainer_session(
        TrainerSessionCreate(client_member_id="member", package_id="bundle", performed_at=now_utc(),
                             duration_minutes=45, focus="Strength"),
        idempotency_key="retry-key", ctx=SimpleNamespace(role=Role.TRAINER, org_id="gym", user_id="trainer-user"),
        session=object(),
    )
    assert result.id == "saved"


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["foreign_member", "foreign_trainer", "banned_trainer", "inactive_trainer"])
async def test_grant_rejects_unavailable_or_foreign_people_before_writes(failure):
    from app.core.constants import MemberStatus, Role
    from app.models.membership import OrganizationMember
    from app.models.user import User
    from app.schemas.staff import TrainerPackageCreate

    member = OrganizationMember(id="member", organization_id="other" if failure == "foreign_member" else "gym",
                                user_id="member-user", role=Role.MEMBER, member_status=MemberStatus.ACTIVE)
    trainer = OrganizationMember(id="trainer", organization_id="other" if failure == "foreign_trainer" else "gym",
                                 user_id="trainer-user", role=Role.TRAINER, banned=failure == "banned_trainer")
    user = User(id="trainer-user", email="trainer@test.com", hashed_password="unused", is_active=failure != "inactive_trainer")

    async def get(_model, key, **_kwargs):
        return {"member": member, "trainer": trainer, "trainer-user": user}.get(key)

    def unexpected_write(_row):
        raise AssertionError("Invalid grants must not write any records")

    with pytest.raises(HTTPException):
        await packages.create_package(SimpleNamespace(get=get, add=unexpected_write), org_id="gym", actor_id="owner",
                                       data=TrainerPackageCreate(member_id="member", trainer_member_id="trainer",
                                                                 name="Ten sessions", total_sessions=10))


@pytest.mark.asyncio
async def test_session_log_consumes_once_and_rolls_back_with_its_transaction():
    from sqlalchemy import create_engine
    from sqlmodel import Session, SQLModel, select

    from app.core.constants import MemberStatus, Role
    from app.models.membership import OrganizationMember
    from app.models.trainer_session import TrainerSessionLog
    from app.models.user import User
    from app.schemas.staff import TrainerPackageCreate, TrainerSessionCreate
    from app.services.trainer_sessions_service import create_log

    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            class AsyncFacade:
                async def get(self, *args, **kwargs):
                    return db.get(*args, **kwargs)

                async def execute(self, statement):
                    return db.execute(statement)

                async def flush(self):
                    db.flush()

                def add(self, row):
                    db.add(row)

            session = AsyncFacade()
            db.add_all([
                User(id="member-user", email="member@test.com", hashed_password="unused"),
                User(id="trainer-user", email="trainer@test.com", hashed_password="unused"),
                OrganizationMember(id="member", organization_id="gym", user_id="member-user",
                                   role=Role.MEMBER, member_status=MemberStatus.ACTIVE),
                OrganizationMember(id="trainer", organization_id="gym", user_id="trainer-user", role=Role.TRAINER),
            ])
            db.flush()
            bundle = await packages.create_package(session, org_id="gym", actor_id="owner", data=TrainerPackageCreate(
                member_id="member", trainer_member_id="trainer", name="One session", total_sessions=1))
            bundle_id = bundle.id
            db.commit()
            data = TrainerSessionCreate(client_member_id="member", package_id=bundle_id,
                                        performed_at=now_utc() - timedelta(minutes=5), duration_minutes=45,
                                        focus="Strength", notes="Private training notes")
            await create_log(session, org_id="gym", trainer_member_id="trainer", actor_id="trainer-user", data=data)
            db.rollback()
            assert db.get(TrainerPackage, bundle_id).used_sessions == 0
            assert db.exec(select(TrainerSessionLog)).all() == []
            saved = await create_log(session, org_id="gym", trainer_member_id="trainer", actor_id="trainer-user", data=data)
            db.commit()
            assert saved.package_id == bundle_id
            assert db.get(TrainerPackage, bundle_id).used_sessions == 1
            with pytest.raises(HTTPException) as error:
                await create_log(session, org_id="gym", trainer_member_id="trainer", actor_id="trainer-user", data=data)
            assert error.value.status_code == 409
            assert len(db.exec(select(TrainerSessionLog)).all()) == 1
            assert (await packages.list_packages(session, org_id="other")) == []
            assert (await packages.list_packages(session, org_id="gym"))[0]["status"] == "complete"
            from app.services.privacy_service import erase_member_from_workspace

            await erase_member_from_workspace(session, org_id="gym", actor_id="owner",
                                               member=db.get(OrganizationMember, "member"),
                                               user=db.get(User, "member-user"))
            db.commit()
            assert db.get(TrainerPackage, bundle_id).cancelled_at is not None
            assert db.get(TrainerPackage, bundle_id).name == "Erased member training credits"
            assert db.get(TrainerSessionLog, saved.id).notes == ""
    finally:
        engine.dispose()


def test_package_migration_preserves_existing_logs_and_checks_credit_quantity(monkeypatch):
    from importlib import import_module

    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import create_engine
    from sqlalchemy.exc import IntegrityError

    migration = import_module("app.db.migrations.versions.g9b0c1d2e3f4_trainer_packages")
    engine = create_engine("sqlite://")
    try:
        with engine.begin() as connection:
            for table in ("organizations", "organization_members", "users"):
                connection.exec_driver_sql(f"CREATE TABLE {table} (id VARCHAR PRIMARY KEY)")
            connection.exec_driver_sql("CREATE TABLE trainer_session_logs (id VARCHAR PRIMARY KEY)")
            connection.exec_driver_sql("INSERT INTO trainer_session_logs VALUES ('existing')")
            monkeypatch.setattr(migration, "op", Operations(MigrationContext.configure(connection)))
            migration.upgrade()
            assert connection.exec_driver_sql("SELECT package_id FROM trainer_session_logs").scalar_one() is None
            with pytest.raises(IntegrityError):
                connection.exec_driver_sql("INSERT INTO trainer_packages (id, created_at, updated_at, organization_id, member_id, trainer_member_id, granted_by_user_id, name, total_sessions, used_sessions, granted_at) VALUES ('bad', '2026-01-01', '2026-01-01', 'gym', 'member', 'trainer', 'owner', 'Empty', 0, 0, '2026-01-01')")
            migration.downgrade()
            assert connection.exec_driver_sql("SELECT id FROM trainer_session_logs").scalar_one() == "existing"
    finally:
        engine.dispose()
