import json
import tempfile
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException, UploadFile
from sqlalchemy import create_engine
from sqlmodel import Session, SQLModel, select

from app.api.v1.routes import members as routes
from app.core.constants import MemberStatus, Role
from app.core.tenancy import TenantContext
from app.models.membership import OrganizationMember
from app.models.organization import Organization
from app.models.user import User
from app.services import members_service as service


@pytest.mark.parametrize('mapping', [
    {'email': 'Missing'}, {'email': 'Contact', 'phone': 'Contact'},
    {'email': 'Contact', 'role': 'Name'}, {'email': ['Contact']}, {},
])
def test_mapping_rejects_unknown_and_conflicting_columns(mapping):
    with pytest.raises(HTTPException) as error:
        service.parse_import_csv(b'Contact,Name\na@example.com,Alice', mapping)
    assert error.value.status_code == 422


def test_custom_mapping_split_names_and_duplicate_errors():
    _, mapping, rows = service.parse_import_csv(
        b'Contact,Given,Surname,Cell\nA@example.com,Alice,Member,123\na@example.com,Another,Name,456\nbad,Bad,Email,789',
        {'email': 'Contact', 'first_name': 'Given', 'last_name': 'Surname', 'phone': 'Cell'},
    )
    assert rows[0]['full_name'] == 'Alice Member'
    assert rows[0]['email'] == 'a@example.com'
    assert rows[1]['error'].startswith('duplicate email')
    assert rows[2]['error'] == 'invalid or missing email'
    assert mapping['phone'] == 'Cell'
    headers, _, rows = service.parse_import_csv(b'Contact,Given\na@example.com,Alice', allow_unmapped=True)
    assert headers == ['Contact', 'Given'] and rows == []


def test_entire_import_limit_is_validated_before_writes():
    with pytest.raises(HTTPException) as error:
        service.parse_import_csv(b'email\n' + b'a@example.com\n' * 10_001)
    assert error.value.status_code == 413


class Facade:
    def __init__(self, db):
        self.db = db

    async def get(self, *args):
        return self.db.get(*args)

    async def execute(self, statement):
        return self.db.execute(statement)

    async def flush(self):
        self.db.flush()

    def add(self, row):
        self.db.add(row)

    def get_bind(self):
        return self.db.get_bind()

    @asynccontextmanager
    async def begin_nested(self):
        with self.db.begin_nested():
            yield


@pytest.fixture
def database():
    engine = create_engine('sqlite://')
    SQLModel.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(Organization(id='gym', name='Gym', org_code='GYM-1'))
        for key, role, org in [('member', Role.MEMBER, 'gym'), ('staff', Role.TRAINER, 'gym'),
                               ('other', Role.MEMBER, 'elsewhere')]:
            db.add(User(id=key, email=f'{key}@example.com', full_name='Shared account name', hashed_password='unused'))
            db.add(OrganizationMember(id=key, organization_id=org, user_id=key, role=role,
                                      member_status=MemberStatus.ACTIVE))
        db.flush()
        yield db, Facade(db)
    engine.dispose()


async def test_preview_is_tenant_scoped_and_does_not_write(database):
    db, session = database
    content = b'email,full_name,phone\nmember@example.com,New Name,123\nother@example.com,Other,456\nstaff@example.com,Staff,789'
    result = await service.preview_import(session, org_id='gym', csv_bytes=content)
    assert [row['action'] for row in result['rows']] == ['existing', 'add', 'existing']
    assert result['rows'][0]['fillable_fields'] == ['display_name', 'phone']
    assert result['rows'][2]['fillable_fields'] == []
    assert not db.new and not db.dirty
    assert db.get(OrganizationMember, 'member').phone is None


async def test_fill_missing_preserves_shared_identity_roles_and_existing_values(database):
    db, session = database
    member = db.get(OrganizationMember, 'member')
    member.phone = 'keep-this'
    content = b'email,full_name,phone\nmember@example.com,Imported Name,replace\nstaff@example.com,Staff,999'
    result = await service.bulk_import_csv(session, org_id='gym', csv_bytes=content, actor_id='owner', fill_missing=True)
    assert result == {'created': 0, 'updated': 1, 'skipped': 1, 'errors': []}
    assert member.phone == 'keep-this' and member.display_name == 'Imported Name'
    assert member.member_status == MemberStatus.ACTIVE
    assert db.get(User, 'member').full_name == 'Shared account name'
    assert db.get(OrganizationMember, 'staff').phone is None
    assert db.get(OrganizationMember, 'other').display_name is None
    again = await service.bulk_import_csv(session, org_id='gym', csv_bytes=content, actor_id='owner', fill_missing=True)
    assert again['updated'] == 0 and again['skipped'] == 2


def upload(content):
    stream = tempfile.SpooledTemporaryFile(max_size=3_000_000)
    stream.write(content)
    stream.seek(0)
    return UploadFile(stream, filename='members.csv')


async def test_import_replay_does_not_resend_activation_and_changed_file_is_rejected(database, monkeypatch):
    db, session = database
    mail = AsyncMock(return_value=True)
    monkeypatch.setattr(service, 'send_email_safe', mail)
    monkeypatch.setattr(service.verif, 'issue_link_token', AsyncMock(return_value='activation'))
    content = b'email,full_name\nnew@example.com,New Member'
    async def apply(body, key='key-1'):
        file = upload(body)
        try:
            return await routes.bulk_import(file=file, column_mapping='null', fill_missing=False,
                idempotency_key=key, ctx=TenantContext('owner', 'gym', Role.OWNER),
                org=db.get(Organization, 'gym'), session=session)
        finally:
            await file.close()
    first = await apply(content)
    second = await apply(content)
    assert first == second and first.created == 1
    mail.assert_awaited_once()
    assert len(db.execute(select(OrganizationMember).where(OrganizationMember.organization_id == 'gym')).all()) == 3
    with pytest.raises(HTTPException) as error:
        await apply(content + b'\nchanged@example.com,Changed')
    assert error.value.status_code == 422
    assert json.loads(first.model_dump_json())['updated'] == 0
