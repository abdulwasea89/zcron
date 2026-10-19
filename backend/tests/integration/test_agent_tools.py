"""Agent tools: org scoping and the guarded-write flow (ADR 018).

The provider is replaced by a scripted model, so these tests drive the same
ReAct loop — including a tool call that interrupts for confirmation — with no
vendor. A failure here is a plumbing failure, not a Groq failure.
"""

from __future__ import annotations

import json

import pytest
from langchain_core.messages import AIMessage
from sqlmodel import select

from app.agent.context import AgentContext, bind_context, clear_context
from app.agent.model import StubChatModel
from app.agent.tools.read import list_plans, list_pending_receipts
from app.agent.tools.write import lock_payroll
from app.core.constants import MemberStatus, Role
from app.models.audit_log import AuditLog
from app.models.membership import OrganizationMember

from tests.helpers import latest_code_for, provision_org

MEMBER_PWD = "M3mberStr0ng!Pwd"


@pytest.fixture(autouse=True)
def stub_provider(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.groq_api_key", "")


def _frames(text: str) -> list[dict]:
    out: list[dict] = []
    for line in text.splitlines():
        if line.startswith("data:"):
            out.append(json.loads(line[len("data:") :].strip()))
    return out


async def _add_member(client, db, *, org_code: str, org_id: str, email: str) -> str:
    """Run the member signup flow and return the new member's id."""

    await client.post(
        "/api/v1/memberships/signup/request-email", json={"org_code": org_code, "email": email}
    )
    code = latest_code_for(email)
    await client.post(
        "/api/v1/memberships/signup/verify-email",
        json={"org_code": org_code, "email": email, "code": code},
    )
    await client.post(
        "/api/v1/memberships/signup/set-password",
        json={"org_code": org_code, "email": email, "password": MEMBER_PWD},
    )
    member = (
        await db.execute(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == org_id,
                OrganizationMember.role == "member",
            )
        )
    ).scalars().first()
    assert member is not None
    # Freezing an unpaid signup is intentionally rejected by the membership
    # service. Seed the active-state precondition for this guarded-write test.
    member.member_status = MemberStatus.ACTIVE
    db.add(member)
    await db.flush()
    return member.id


# --------------------------------------------------------------------------- #
# Read tools
# --------------------------------------------------------------------------- #


async def test_read_tool_returns_only_the_bound_orgs_data(client, db):
    org_code_a, headers_a, org_a = await provision_org(client, email="a@g.com", name="Org A")
    _, _, org_b = await provision_org(client, email="b@g.com", name="Org B")

    # Publish a plan in Org A.
    created = await client.post(
        "/api/v1/plans",
        headers=headers_a,
        json={
            "name": "Monthly",
            "price": 149.0,
            "billing_type": "recurring",
            "cycle_unit": "month",
            "cycle_length": 1,
        },
    )
    await client.post(f"/api/v1/plans/{created.json()['id']}/publish", headers=headers_a)

    async def plans_for(org_id: str) -> list[dict]:
        token = bind_context(AgentContext(org_id=org_id, user_id="u1", role=Role.OWNER, session=db))
        try:
            return json.loads(await list_plans.ainvoke({}))
        finally:
            clear_context(token)

    assert [p["name"] for p in await plans_for(org_a)] == ["Monthly"]
    # Org B's assistant cannot see Org A's plan.
    assert await plans_for(org_b) == []


async def test_pending_receipts_tool_is_empty_by_default(client, db):
    _, _, org_id = await provision_org(client, email="owner@g.com", name="Iron Pulse")

    token = bind_context(AgentContext(org_id=org_id, user_id="u1", role=Role.OWNER, session=db))
    try:
        receipts = json.loads(await list_pending_receipts.ainvoke({}))
    finally:
        clear_context(token)
    assert receipts == []


# --------------------------------------------------------------------------- #
# Guarded writes
# --------------------------------------------------------------------------- #


async def test_write_tool_denied_for_role_without_capability(client, db):
    _, _, org_id = await provision_org(client, email="owner@g.com", name="Iron Pulse")

    token = bind_context(AgentContext(org_id=org_id, user_id="u1", role=Role.MANAGER, session=db))
    try:
        # Payroll is owner-only, so a manager is refused before any confirmation.
        result = json.loads(await lock_payroll.ainvoke({"run_id": "run-1"}))
    finally:
        clear_context(token)
    assert result["status"] == "not_permitted"


async def test_guarded_write_interrupts_then_executes_on_approval(client, db, monkeypatch):
    """A write pauses for confirmation, then runs — once — after approval."""

    org_code, headers, org_id = await provision_org(client, email="owner@g.com", name="Iron Pulse")
    member_id = await _add_member(client, db, org_code=org_code, org_id=org_id, email="m@g.com")

    # Script: the model asks to freeze the member, then, after the tool result,
    # writes a final answer. One shared model instance so the script survives
    # the interrupt/resume boundary.
    model = StubChatModel(
        script=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "change_member_status",
                        "args": {"member_id": member_id, "action": "freeze", "reason": "test"},
                        "id": "call_freeze",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="Done — the member is frozen."),
        ]
    )
    monkeypatch.setattr("app.agent.graph.build_chat_model", lambda **kw: model)

    conv = (
        await client.post(
            "/api/v1/assistant/conversations",
            headers={**headers, "Idempotency-Key": "key-create"},
            json={"content": "Freeze the new member"},
        )
    ).json()

    # First pass: the run pauses at the confirmation.
    r = await client.post(
        f"/api/v1/assistant/conversations/{conv['id']}/stream", headers=headers, json={}
    )
    frames = _frames(r.text)
    assert any("interrupt" in f for f in frames), frames
    assert not [f for f in frames if f.get("done")]

    # The member is untouched until the human says yes.
    member = await db.get(OrganizationMember, member_id)
    assert member is not None and member.member_status.value != "frozen"

    # Confirm.
    r = await client.post(
        f"/api/v1/assistant/conversations/{conv['id']}/resume",
        headers={**headers, "Idempotency-Key": "key-resume"},
        json={"resume": {"approved": True}},
    )
    frames = _frames(r.text)
    assert [f for f in frames if f.get("done")], frames

    await db.refresh(member)
    assert member.member_status.value == "frozen"

    # The write is audited with the owner as actor.
    audits = (
        await db.execute(
            select(AuditLog).where(
                AuditLog.organization_id == org_id,
                AuditLog.action == "member.freeze",
            )
        )
    ).scalars().all()
    assert len(audits) == 1

    # And the final answer is in the transcript.
    detail = (
        await client.get(f"/api/v1/assistant/conversations/{conv['id']}", headers=headers)
    ).json()
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]
    assert "frozen" in detail["messages"][1]["content"].lower()


async def test_guarded_write_rejected_leaves_state_unchanged(client, db, monkeypatch):
    org_code, headers, org_id = await provision_org(client, email="owner@g.com", name="Iron Pulse")
    member_id = await _add_member(client, db, org_code=org_code, org_id=org_id, email="m@g.com")

    model = StubChatModel(
        script=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "change_member_status",
                        "args": {"member_id": member_id, "action": "ban", "reason": "test"},
                        "id": "call_ban",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="Understood, nothing was changed."),
        ]
    )
    monkeypatch.setattr("app.agent.graph.build_chat_model", lambda **kw: model)

    conv = (
        await client.post(
            "/api/v1/assistant/conversations",
            headers={**headers, "Idempotency-Key": "key-create"},
            json={"content": "Ban the new member"},
        )
    ).json()
    await client.post(
        f"/api/v1/assistant/conversations/{conv['id']}/stream", headers=headers, json={}
    )
    r = await client.post(
        f"/api/v1/assistant/conversations/{conv['id']}/resume",
        headers={**headers, "Idempotency-Key": "key-resume"},
        json={"resume": {"approved": False}},
    )
    assert [f for f in _frames(r.text) if f.get("done")]

    member = await db.get(OrganizationMember, member_id)
    assert member is not None and member.member_status.value != "banned"
    assert (
        await db.execute(
            select(AuditLog).where(
                AuditLog.organization_id == org_id, AuditLog.action == "member.ban"
            )
        )
    ).scalars().all() == []
