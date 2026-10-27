from datetime import datetime
from types import SimpleNamespace

from app.api.v1.routes.members import member_activity
from app.core.constants import Role
from app.core.tenancy import TenantContext


class Result:
    def __init__(self, rows):
        self.rows = rows

    def scalars(self):
        return self

    def all(self):
        return self.rows


class ActivitySession:
    def __init__(self, member, actor):
        self.member = member
        self.actor = actor
        self.statements = []

    async def get(self, _model, _id):
        return self.member

    async def execute(self, statement):
        sql = str(statement)
        self.statements.append(sql)
        if "FROM attendance" in sql:
            rows = [SimpleNamespace(
                id="visit", checked_in_at=datetime(2026, 10, 27), method=SimpleNamespace(value="manual"),
                checked_in_by="staff",
            )]
        elif "FROM payments" in sql:
            rows = [SimpleNamespace(
                id="payment", paid_at=None, created_at=datetime(2026, 10, 26),
                status=SimpleNamespace(value="succeeded"), amount=25, currency="USD", logged_by="staff",
            )]
        elif "FROM inbox_messages" in sql:
            rows = [(SimpleNamespace(
                id="message", created_at=datetime(2026, 10, 25), direction=SimpleNamespace(value="inbound"),
                delivery_status="delivered", sender_user_id=None,
            ), SimpleNamespace(value="email"))]
        elif "FROM audit_logs" in sql:
            rows = [SimpleNamespace(
                id="audit", created_at=datetime(2026, 10, 24), action="member.tags_updated",
                actor_user_id="staff",
            )]
        else:
            rows = [("staff", "Front Desk")]
        return Result(rows)


async def test_member_activity_merges_events_and_audits_history_reads(monkeypatch):
    from app.api.v1.routes import members

    member = SimpleNamespace(id="member", organization_id="gym")
    session = ActivitySession(member, "staff")
    audit_events = []

    async def record_audit(_session, **kwargs):
        audit_events.append(kwargs)

    monkeypatch.setattr(members, "record_audit", record_audit)
    request = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"), headers={"user-agent": "unit-test"})
    events = await member_activity("member", request, TenantContext("staff", "gym", Role.OWNER), session)

    assert {event["type"] for event in events} == {"visit", "payment", "message", "staff_action"}
    assert [event["type"] for event in events] == ["visit", "payment", "message", "staff_action"]
    assert events[-1]["title"] == "Tags Updated"
    assert sum(event["actor_name"] == "Front Desk" for event in events) == 3
    assert all("organization_id" in query for query in session.statements[:4])
    assert all("body" not in event and "metadata_json" not in event for event in events)
    assert audit_events == [{
        "action": "member.activity_viewed", "organization_id": "gym", "actor_user_id": "staff",
        "entity_type": "member", "entity_id": "member", "ip_address": "127.0.0.1",
        "user_agent": "unit-test",
    }]
    assert "audit_logs.action !=" in session.statements[-2]
