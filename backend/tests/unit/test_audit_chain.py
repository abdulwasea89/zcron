from types import SimpleNamespace

import pytest

from app.models.audit_log import AuditLog
from app.services.audit_service import audit_entry_digest, record_audit, verify_audit_chain


def test_hash_chain_detects_changed_and_missing_events():
    first = AuditLog(organization_id="gym", action="member.updated")
    first.entry_hash = audit_entry_digest(first)
    second = AuditLog(organization_id="gym", action="payment.logged", previous_hash=first.entry_hash)
    second.entry_hash = audit_entry_digest(second)

    assert verify_audit_chain([first, second], second.entry_hash) == {
        "valid": True, "checked": 2, "legacy": 0,
    }

    second.action = "payment.deleted"
    assert verify_audit_chain([first, second], second.entry_hash)["valid"] is False
    second.action = "payment.logged"
    assert verify_audit_chain([second], second.entry_hash)["valid"] is False


def test_hash_chain_reports_preexisting_unhashed_events():
    legacy = AuditLog(organization_id="gym", action="old.event")
    current = AuditLog(organization_id="gym", action="new.event")
    current.entry_hash = audit_entry_digest(current)

    assert verify_audit_chain([legacy, current], current.entry_hash) == {
        "valid": True, "checked": 1, "legacy": 1,
    }


def test_lane_key_is_covered_by_hash_without_changing_legacy_main_chain_digest():
    entry = AuditLog(organization_id="gym", action="privacy.data_accessed", chain_key="read:staff")
    entry.entry_hash = audit_entry_digest(entry)
    assert verify_audit_chain([entry], entry.entry_hash)["valid"] is True
    entry.chain_key = "read:other-staff"
    assert verify_audit_chain([entry], entry.entry_hash)["valid"] is False


@pytest.mark.asyncio
async def test_read_audit_lane_advances_without_locking_organization():
    from app.models.audit_chain_head import AuditChainHead
    head = AuditChainHead(organization_id="gym", chain_key="read:staff")

    class Session:
        statements = []
        entries = []

        def get_bind(self):
            return SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))

        async def execute(self, statement):
            self.statements.append(str(statement))
            return SimpleNamespace(scalar_one=lambda: head)

        def add(self, item):
            if isinstance(item, AuditLog):
                self.entries.append(item)

    session = Session()
    first = await record_audit(session, organization_id="gym", actor_user_id="staff",
                               action="privacy.data_accessed", chain_key="read:staff")
    second = await record_audit(session, organization_id="gym", actor_user_id="staff",
                                action="privacy.data_accessed", chain_key="read:staff")
    assert second.previous_hash == first.entry_hash
    assert head.head_hash == second.entry_hash
    assert len(session.entries) == 2
    assert all("organizations" not in statement for statement in session.statements)


@pytest.mark.asyncio
async def test_record_audit_advances_the_organization_chain():
    organization = SimpleNamespace(audit_chain_head=None)

    class Session:
        entries = []

        async def execute(self, _statement):
            return SimpleNamespace(scalar_one_or_none=lambda: organization)

        def add(self, entry):
            if isinstance(entry, AuditLog):
                self.entries.append(entry)

    session = Session()
    first = await record_audit(session, organization_id="gym", action="first")
    second = await record_audit(session, organization_id="gym", action="second")

    assert first.previous_hash is None
    assert second.previous_hash == first.entry_hash
    assert organization.audit_chain_head == second.entry_hash
    assert verify_audit_chain(session.entries, organization.audit_chain_head)["valid"] is True
