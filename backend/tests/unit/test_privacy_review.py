import importlib

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine, inspect
from sqlmodel import Session, SQLModel

from app.api.v1.routes import data_subject_requests as routes
from app.core.constants import MemberStatus, Role, SubscriptionStatus
from app.core.tenancy import TenantContext
from app.db.session import _upgrade_sqlite_late_migration_columns
from app.models.data_subject_request import DataSubjectRequest
from app.models.membership import OrganizationMember
from app.models.organization import Organization
from app.models.session import AuthSession
from app.models.subscription import Subscription
from app.models.user import User
from app.schemas.privacy import DataSubjectRequestDecision, PrivacyReviewUpdate
from app.services.privacy_service import erase_member_from_workspace


class Facade:
    def __init__(self, db):
        self.db = db

    async def get(self, *args):
        return self.db.get(*args)

    async def execute(self, statement):
        return self.db.execute(statement)

    def get_bind(self):
        return self.db.get_bind()

    async def flush(self):
        self.db.flush()

    def add(self, row):
        self.db.add(row)


@pytest.fixture
def database():
    engine = create_engine('sqlite://')
    SQLModel.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(Organization(id='gym', name='Gym', org_code='GYM-1'))
        db.add(User(id='user', email='member@example.com', hashed_password='unused'))
        db.add(OrganizationMember(id='member', organization_id='gym', user_id='user', role=Role.MEMBER,
                                  member_status=MemberStatus.ACTIVE, health_notes='private'))
        db.add(DataSubjectRequest(id='request', organization_id='gym', member_id='member',
                                  member_name='Name', member_email='member@example.com',
                                  request_type='erasure', created_by='owner'))
        db.flush()
        yield db, Facade(db), TenantContext('owner', 'gym', Role.OWNER)
    engine.dispose()


@pytest.mark.parametrize('data', [
    {'item': 'identity', 'outcome': 'not_applicable', 'note': 'We did not check identity.'},
    {'item': 'processors', 'outcome': 'verified', 'note': '          '},
    {'item': 'unknown', 'outcome': 'verified', 'note': 'A reference for the review.'},
])
def test_review_requires_valid_item_and_substantive_evidence(data):
    with pytest.raises(ValidationError):
        PrivacyReviewUpdate(**data)


async def save(session, ctx, item, key=None):
    return await routes.record_privacy_review('request',
        PrivacyReviewUpdate(item=item, outcome='verified', note=f'Checked {item}; reference ABC123.'),
        ctx=ctx, session=session, idempotency_key=key or item)


async def decide(session, ctx, status, key):
    return await routes.decide_data_request('request',
        DataSubjectRequestDecision(status=status, resolution_note='Reviewed retained records and external actions.'),
        ctx=ctx, session=session, idempotency_key=key)


async def test_checks_block_premature_erasure_and_closure(database):
    db, session, ctx = database
    with pytest.raises(HTTPException) as error:
        await decide(session, ctx, 'in_review', 'premature-start')
    assert error.value.status_code == 409
    assert db.get(OrganizationMember, 'member').health_notes == 'private'
    await save(session, ctx, 'identity')
    with pytest.raises(HTTPException) as error:
        await decide(session, ctx, 'completed', 'no-redaction')
    assert error.value.status_code == 409
    reviewed = await decide(session, ctx, 'in_review', 'start')
    assert reviewed.erasure_redacted_at
    with pytest.raises(HTTPException) as error:
        await decide(session, ctx, 'completed', 'missing-checks')
    assert error.value.status_code == 409
    for item in ('linked_records', 'processors', 'retention_backups'):
        await save(session, ctx, item)
    complete = await decide(session, ctx, 'completed', 'finish')
    replay = await decide(session, ctx, 'completed', 'finish')
    assert complete == replay and complete.status == 'completed'
    assert len(complete.review_checks) == 4
    with pytest.raises(HTTPException) as error:
        await save(session, ctx, 'processors', 'changed-after-close')
    assert error.value.status_code == 409


async def test_review_is_scoped_and_replay_does_not_replace_evidence(database):
    db, session, ctx = database
    with pytest.raises(HTTPException) as error:
        await save(session, TenantContext('owner', 'other', Role.OWNER), 'identity')
    assert error.value.status_code == 404
    assert db.get(DataSubjectRequest, 'request').review_checks == {}
    first = await save(session, ctx, 'identity')
    again = await save(session, ctx, 'identity')
    assert first.review_checks == again.review_checks
    assert first.review_checks['identity']['reviewed_by'] == 'owner'


async def test_shared_identity_and_other_gym_access_are_preserved(database):
    db, session, ctx = database
    db.add(OrganizationMember(id='other-member', organization_id='other', user_id='user', role=Role.MEMBER,
                              member_status=MemberStatus.ACTIVE, health_notes='other gym notes'))
    for gym, member in [('gym', 'member'), ('other', 'other-member')]:
        db.add(AuthSession(id=gym, user_id='user', organization_id=gym, refresh_token_hash=gym))
        db.add(Subscription(id=gym, organization_id=gym, member_id=member, plan_id='plan',
                            status=SubscriptionStatus.ACTIVE, auto_renew=True))
    db.flush()
    await save(session, ctx, 'identity')
    await decide(session, ctx, 'in_review', 'shared-review')
    member = db.get(OrganizationMember, 'member')
    assert member.banned and member.health_notes is None
    assert db.get(User, 'user').email == 'member@example.com'
    assert db.get(User, 'user').is_active
    assert db.get(OrganizationMember, 'other-member').health_notes == 'other gym notes'
    assert db.get(AuthSession, 'gym').revoked
    assert not db.get(AuthSession, 'other').revoked
    assert not db.get(Subscription, 'gym').auto_renew
    assert db.get(Subscription, 'other').auto_renew


async def test_erasure_does_not_affect_promoted_staff_or_wrong_tenant(database):
    db, session, _ctx = database
    member, user = db.get(OrganizationMember, 'member'), db.get(User, 'user')
    with pytest.raises(HTTPException) as error:
        await erase_member_from_workspace(session, org_id='other', member=member, user=user, actor_id='owner')
    assert error.value.status_code == 404
    member.role = Role.TRAINER
    with pytest.raises(HTTPException) as error:
        await erase_member_from_workspace(session, org_id='gym', member=member, user=user, actor_id='owner')
    assert error.value.status_code == 409
    assert not member.banned and user.is_active


def test_upgrade_preserves_old_requests_and_local_compatibility_is_repeatable():
    module = importlib.import_module('app.db.migrations.versions.j2e3f4g5h6i7_privacy_review_checks')
    engine = create_engine('sqlite://')
    with engine.begin() as connection:
        connection.exec_driver_sql('CREATE TABLE data_subject_requests (id VARCHAR PRIMARY KEY, note VARCHAR)')
        connection.exec_driver_sql("INSERT INTO data_subject_requests (id,note) VALUES ('old','keep evidence')")
        with Operations.context(MigrationContext.configure(connection)):
            module.upgrade()
        assert connection.exec_driver_sql('SELECT review_checks, note FROM data_subject_requests').one() == ('{}', 'keep evidence')
        _upgrade_sqlite_late_migration_columns(connection)
        _upgrade_sqlite_late_migration_columns(connection)
        assert 'review_checks' in {column['name'] for column in inspect(connection).get_columns('data_subject_requests')}
    engine.dispose()
