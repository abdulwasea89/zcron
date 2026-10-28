from unittest.mock import AsyncMock

import pytest

from app.workers import celery_app as workers


@pytest.mark.asyncio
async def test_tenant_sweep_uses_one_transaction_per_org(monkeypatch):
    class OrgIds:
        def scalars(self):
            return self

        def all(self):
            return ["org-a", "org-b"]

    class Session:
        def __init__(self, discovery=False):
            self.discovery = discovery
            self.committed = False

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def execute(self, _query):
            return OrgIds()

        async def commit(self):
            self.committed = True

    class Factory:
        def __init__(self):
            self.sessions = []

        def __call__(self):
            session = Session(discovery=not self.sessions)
            self.sessions.append(session)
            return session

    factory = Factory()
    set_context = AsyncMock()
    monkeypatch.setattr(workers, "async_session_maker", factory)
    monkeypatch.setattr(workers, "set_rls_context", set_context)

    async def process(_session, org_id):
        if org_id == "org-b":
            raise RuntimeError("tenant failed")
        return {"ok": True}

    result = await workers._for_each_org(process)

    assert result == {"orgs": 2, "results": {"org-a": {"ok": True}, "org-b": {"error": "tenant failed"}}}
    assert len(factory.sessions) == 3
    assert factory.sessions[0].committed is False
    assert factory.sessions[1].committed is True
    assert factory.sessions[2].committed is False
    assert set_context.await_count == 3
