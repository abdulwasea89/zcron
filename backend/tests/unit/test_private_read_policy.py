import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.api import deps
from app.agent.context import AgentContext, bind_context, clear_context
from app.agent.swarm.orchestrator import _run_one
from app.agent.swarm.types import Assignment, Finding, Specialist
from app.agent.tools.read import list_payroll_runs
from app.core.constants import MemberStatus, Role
from app.core.tenancy import TenantContext
from app.models.organization import Organization
from app.models.session import AuthSession
from app.models.user import User
from app.services.data_access_service import record_read_access


def request(path='/api/v1/members/member-1', method='GET'):
    return Request({'type': 'http', 'method': method, 'path': path,
                    'query_string': b'search=private-health-note',
                    'headers': [(b'x-forwarded-for', b'203.0.113.8'), (b'user-agent', b'admin-browser')],
                    'path_params': {'member_id': 'member-1'},
                    'route': SimpleNamespace(path='/api/v1/members/{member_id}')})


@pytest.mark.parametrize('inactive,banned,wrong_session,expected', [
    (False, False, False, None), (True, False, False, 401),
    (False, True, False, 403), (False, False, True, 401),
])
async def test_current_membership_overrides_old_owner_token(monkeypatch, inactive, banned, wrong_session, expected):
    monkeypatch.setattr(deps, 'safe_decode', lambda _: {
        'type': deps.ACCESS, 'sub': 'user', 'org_id': 'org', 'role': 'owner', 'session_id': 'session'})
    membership = SimpleNamespace(role=Role.FRONT_DESK, banned=False,
                                 member_status=MemberStatus.BANNED if banned else MemberStatus.ACTIVE)

    async def get(model, key):
        return {User: SimpleNamespace(is_active=not inactive),
                Organization: SimpleNamespace(onboarding_complete=True),
                AuthSession: SimpleNamespace(revoked=False, user_id='other' if wrong_session else 'user',
                                             organization_id='org')}[model]

    session = SimpleNamespace(get=get, execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: membership)))
    req = request()
    if expected:
        with pytest.raises(HTTPException) as exc:
            await deps.get_tenant(req, 'Bearer token', 'org', session)
        assert exc.value.status_code == expected
        assert not hasattr(req.state, 'tenant')
    else:
        ctx = await deps.get_tenant(req, 'Bearer token', 'org', session)
        assert ctx.role == Role.FRONT_DESK
        assert req.state.tenant == ctx


@pytest.mark.parametrize('path', ['/api/v1/members/member-1', '/api/v1/privacy/requests',
                                  '/api/v1/win-back', '/api/v1/finance/export'])
async def test_private_reads_audit_scope_without_search_values(path):
    req = request(path)
    req.state.tenant = TenantContext('actor', 'gym', Role.MANAGER)
    entries = []
    class AuditSession:
        def add(self, entry):
            entries.append(entry)

        async def execute(self, _statement):
            return SimpleNamespace(scalar_one_or_none=lambda: None)

    await record_read_access(AuditSession(), req)
    assert len(entries) == 1
    entry = entries[0]
    assert (entry.organization_id, entry.actor_user_id) == ('gym', 'actor')
    assert json.loads(entry.metadata_json)['identifiers'] == {'member_id': 'member-1'}
    assert json.loads(entry.metadata_json)['access_type'] == ('export' if path.endswith('/export') else 'read')
    assert entry.ip_address == '203.0.113.8'
    assert entry.user_agent == 'admin-browser'
    assert 'private-health-note' not in entry.metadata_json
    assert entry.new_values_json is None


async def test_public_and_failed_requests_are_not_successful_read_audits(monkeypatch):
    from app.db import session as database
    entries = []
    session = SimpleNamespace(add=entries.append, commit=AsyncMock(), rollback=AsyncMock())

    class SessionContext:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *args):
            pass

    monkeypatch.setattr(database, 'async_session_maker', SessionContext)
    req = request()
    await record_read_access(session, req)
    assert entries == []
    req.state.tenant = TenantContext('actor', 'gym', Role.OWNER)
    generator = database.get_session(req)
    assert await anext(generator) is session
    with pytest.raises(HTTPException):
        await generator.athrow(HTTPException(403))
    assert entries == []
    session.rollback.assert_awaited_once()
    session.commit.assert_not_awaited()
    generator = database.get_session(req)
    await anext(generator)
    with pytest.raises(StopAsyncIteration):
        await anext(generator)
    assert len(entries) == 1
    session.commit.assert_awaited_once()


@pytest.mark.parametrize('role', [Role.MANAGER, Role.FRONT_DESK, Role.TRAINER, Role.OWNER])
async def test_payroll_tool_checks_permission_before_query(monkeypatch, role):
    from app.agent.tools import read
    query = AsyncMock(return_value=[])
    monkeypatch.setattr(read.payroll, 'list_runs', query)
    entries = []
    token = bind_context(AgentContext('gym', 'actor', role, SimpleNamespace(add=entries.append)))
    try:
        result = json.loads(await list_payroll_runs.ainvoke({}))
    finally:
        clear_context(token)
    if role == Role.OWNER:
        assert result == []
        query.assert_awaited_once()
        assert entries[0].entity_type == 'payroll'
    else:
        assert result['status'] == 'not_permitted'
        query.assert_not_awaited()
        assert entries == []


@pytest.mark.parametrize('role,fail', [(Role.MANAGER, False), (Role.OWNER, False), (Role.OWNER, True)])
async def test_swarm_payroll_permission_and_sanitized_failures(role, fail):
    runner = AsyncMock(return_value=Finding('pay', 'done', 'Complete'))
    if fail:
        runner.side_effect = RuntimeError('SELECT private_salary FROM users secret')
    specialist = Specialist('pay', 'Payroll', 'payroll', '', '', runner)
    frames, entries = [], []
    ctx = AgentContext('gym', 'actor', role, SimpleNamespace(add=entries.append))
    finding = await _run_one(specialist, Assignment('pay', 'Cost?'), ctx, AsyncMock(), frames.append)
    assert 'private_salary' not in json.dumps(frames)
    if role == Role.MANAGER:
        runner.assert_not_awaited()
        assert finding.status == 'skipped'
    elif fail:
        assert finding.status == 'failed'
    else:
        runner.assert_awaited_once()
        assert len(entries) == 1
