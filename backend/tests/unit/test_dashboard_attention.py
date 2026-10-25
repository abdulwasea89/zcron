from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.v1.routes import analytics
from app.models.membership import OrganizationMember


@pytest.mark.asyncio
async def test_hiding_attention_is_deduplicated_bounded_and_restorable():
    member = OrganizationMember(organization_id="org", user_id="staff")
    member.dashboard_hidden_attention = [f"item:{i}" for i in range(200)]

    class Session:
        def add(self, row):
            assert row is member

        async def execute(self, query):
            assert "organization_members.organization_id" in str(query)
            assert "organization_members.user_id" in str(query)
            return SimpleNamespace(scalar_one_or_none=lambda: member)

    session = Session()
    ctx = SimpleNamespace(is_staff=True, org_id="org", user_id="staff")
    result = await analytics.hide_attention(analytics.DashboardHideIn(key="new-alert"), ctx, session)
    assert len(result["keys"]) == 200 and result["keys"][-1] == "new-alert"
    await analytics.hide_attention(analytics.DashboardHideIn(key="new-alert"), ctx, session)
    assert len(member.dashboard_hidden_attention) == 200
    assert (await analytics.hidden_attention(ctx, session))["keys"][-1] == "new-alert"
    assert await analytics.restore_attention(ctx, session) == {"keys": []}


@pytest.mark.asyncio
async def test_members_cannot_access_staff_dashboard_preferences():
    with pytest.raises(HTTPException) as error:
        await analytics.hidden_attention(SimpleNamespace(is_staff=False), None)
    assert error.value.status_code == 403


def test_dashboard_preference_migration_preserves_existing_members(monkeypatch):
    from importlib import import_module
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import create_engine

    migration = import_module("app.db.migrations.versions.y1z2a3b4c5d6_dashboard_attention_preferences")
    engine = create_engine("sqlite://")
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("CREATE TABLE organization_members (id VARCHAR PRIMARY KEY)")
            connection.exec_driver_sql("INSERT INTO organization_members (id) VALUES ('existing')")
            monkeypatch.setattr(migration, "op", Operations(MigrationContext.configure(connection)))
            migration.upgrade()
            assert connection.exec_driver_sql("SELECT dashboard_hidden_attention FROM organization_members").scalar_one() == "[]"
            migration.downgrade()
            assert connection.exec_driver_sql("SELECT id FROM organization_members").scalar_one() == "existing"
    finally:
        engine.dispose()
