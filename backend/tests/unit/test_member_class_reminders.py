from datetime import timedelta
from types import SimpleNamespace

import pytest

from app.core.security import now_utc
from app.models.class_session import ClassBooking, ClassSession
from app.models.membership import OrganizationMember
from app.models.organization import Organization
from app.models.user import User
from app.workers import class_reminders


@pytest.mark.asyncio
@pytest.mark.parametrize("email_accepted", [True, False])
async def test_booked_member_reminder_is_created_once_and_reports_email_truthfully(monkeypatch, email_accepted):
    org = Organization(id="org", name="Gym", timezone="Asia/Karachi")
    member = OrganizationMember(organization_id=org.id, user_id="user")
    user = User(id="user", email="member@example.com", hashed_password="unused")
    cs = ClassSession(organization_id=org.id, title="Strength", starts_at=now_utc() + timedelta(minutes=30))
    booking = ClassBooking(organization_id=org.id, class_session_id=cs.id, member_id=member.id)
    notifications = []
    emails = []

    class Session:
        async def get(self, *_args):
            return org

        async def execute(self, query):
            sql = str(query)
            assert "class_bookings.reminder_created_at IS NULL" in sql
            assert "class_sessions.cancelled IS false" in sql
            assert "organization_members.banned IS false" in sql
            rows = [] if booking.reminder_created_at else [(booking, cs, member, user)]
            return SimpleNamespace(all=lambda: rows)

        def add(self, value):
            assert value is booking

    async def notify(*_args, **kwargs):
        notifications.append(kwargs)

    async def email(*args):
        emails.append(args)
        return email_accepted

    async def noop(*_args, **_kwargs):
        pass

    monkeypatch.setattr(class_reminders, "create_notification", notify)
    monkeypatch.setattr(class_reminders, "send_email_safe", email)
    monkeypatch.setattr(class_reminders, "record_audit", noop)
    monkeypatch.setattr(class_reminders.events, "class_changed", noop)
    first = await class_reminders.run_member_class_reminders(Session(), org_id=org.id)
    second = await class_reminders.run_member_class_reminders(Session(), org_id=org.id)
    assert first == {"created": 1, "email_accepted": int(email_accepted)}
    assert second == {"created": 0, "email_accepted": 0}
    assert booking.reminder_email_accepted is email_accepted
    assert len(notifications) == len(emails) == 1
    assert "PKT" in emails[0][2]
