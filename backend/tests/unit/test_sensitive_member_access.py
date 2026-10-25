from datetime import datetime
from types import SimpleNamespace

import pytest

from app.api.v1.routes import audit, members
from app.core.constants import Role
from app.core.permissions import Capability, role_has
from app.core.tenancy import TenantContext
from app.models.membership import OrganizationMember
from app.models.user import User


@pytest.mark.parametrize("industry", ["gym", "office", "academy"])
@pytest.mark.parametrize("role", list(Role))
def test_private_field_permissions_do_not_expand_with_industry(role, industry):
    assert role_has(role, Capability.VIEW_PRIVATE_MEMBER_PROFILE, industry) == (role in {Role.OWNER, Role.MANAGER})
    assert role_has(role, Capability.VIEW_STAFF_COMPENSATION, industry) == (role == Role.OWNER)


@pytest.mark.asyncio
@pytest.mark.parametrize("role", [Role.OWNER, Role.MANAGER])
async def test_historical_payroll_values_are_hidden_from_manager_audit(monkeypatch, role):
    async def logs(*_args, **_kwargs):
        return [{"id": "entry", "action": "staff.compensation_updated", "created_at": datetime(2026, 1, 1),
                 "old_values": {"hourly_rate": 10}, "new_values": {"hourly_rate": 20},
                 "metadata": {"net": 1000}}], 1

    monkeypatch.setattr(audit.audit, "list_audit_logs", logs)
    result = await audit.list_audit_logs(ctx=TenantContext("actor", "org", role), session=None, page=1, page_size=50)
    row = result.items[0]
    if role == Role.MANAGER:
        assert row.old_values is None and row.new_values is None
        assert row.metadata == {"redacted": True}
    else:
        assert row.new_values == {"hourly_rate": 20}


@pytest.mark.asyncio
@pytest.mark.parametrize("role", [Role.OWNER, Role.MANAGER])
async def test_directory_compensation_reads_are_owner_only_and_audited(monkeypatch, role):
    member = OrganizationMember(organization_id="org", user_id="staff", role=Role.TRAINER, hourly_rate=20)
    user = User(id="staff", email="staff@example.com", hashed_password="unused")
    audits = []

    async def directory(*_args, **_kwargs):
        return [(member, user)]

    async def names(*_args, **_kwargs):
        return {}

    async def record(*_args, **kwargs):
        audits.append(kwargs)

    monkeypatch.setattr(members.members, "directory", directory)
    monkeypatch.setattr(members, "_trainer_names", names)
    monkeypatch.setattr(members, "record_audit", record)
    result = await members.list_directory(status=None, role=None, ctx=TenantContext("actor", "org", role), session=SimpleNamespace())
    assert (result[0].hourly_rate is not None) == (role == Role.OWNER)
    assert bool(audits) == (role == Role.OWNER)
    if audits:
        assert audits[0]["metadata"] == {"record_count": 1}
