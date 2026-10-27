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
