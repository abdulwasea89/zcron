from datetime import timedelta

import pytest

from app.core.constants import Role
from app.core.security import now_utc
from app.models.class_session import ClassSession
from app.models.notification import Notification
from app.models.membership import OrganizationMember
from app.workers import class_reminders


class Rows:
    def __init__(self, rows):
        self.rows = rows

    def scalars(self):
        return self

    def all(self):
        return self.rows


class Scalar:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


@pytest.mark.asyncio
async def test_trainer_class_reminder_is_created_once(monkeypatch):
    class_session = ClassSession(
        organization_id="org", category="class", title="Strength",
        trainer_member_id="trainer", starts_at=now_utc() + timedelta(minutes=30),
    )
    trainer = OrganizationMember(
        organization_id="org", user_id="trainer-user", role=Role.TRAINER,
    )

    class Session:
        seen = False
        calls = 0

        async def execute(self, _query):
            self.calls += 1
            return Rows([class_session]) if self.calls % 2 else Scalar("notice" if self.seen else None)

        async def get(self, _model, _id):
            return trainer

    session = Session()
    notifications = []

    async def create_notification(session, **data):
        session.seen = True
        notifications.append(data)
        return Notification(organization_id="org", recipient_user_id=data["recipient_user_id"],
                            category=data["category"], title=data["title"], body=data["body"])

    monkeypatch.setattr(class_reminders, "create_notification", create_notification)

    first = await class_reminders.run_class_reminders(session, org_id="org")
    second = await class_reminders.run_class_reminders(session, org_id="org")

    assert first == {"sent": 1, "skipped": 0}
    assert second == {"sent": 0, "skipped": 1}
    assert len(notifications) == 1
    assert notifications[0]["recipient_user_id"] == "trainer-user"
    assert notifications[0]["data"] == {
        "class_session_id": class_session.id,
        "reminder": "one_hour",
    }
