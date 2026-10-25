from datetime import timedelta
from types import SimpleNamespace
import pytest

from app.core.constants import BookingStatus
from app.core.security import now_utc
from app.models.class_session import ClassBooking, ClassSession
from app.models.staff import Task
from app.services import classes_service


class Result:
    def __init__(self, row):
        self.row = row

    def scalar_one_or_none(self):
        return self.row


class Session:
    def __init__(self, rows, booking):
        self.rows = iter(rows)
        self.booking = booking

    async def execute(self, _query):
        return Result(next(self.rows))

    async def get(self, _model, _key, **_kwargs):
        return self.booking

    def add(self, _row):
        pass


@pytest.mark.asyncio
async def test_staff_cancellation_promotes_waitlist_without_changing_capacity(monkeypatch):
    class_session = ClassSession(
        organization_id="org", title="Strength", starts_at=now_utc() + timedelta(days=1),
        capacity=1, booked_count=1,
    )
    booked = ClassBooking(
        organization_id="org", class_session_id=class_session.id, member_id="member-1",
        status=BookingStatus.BOOKED,
    )
    waiting = ClassBooking(
        organization_id="org", class_session_id=class_session.id, member_id="member-2",
        status=BookingStatus.WAITLISTED,
    )
    session = Session([class_session, waiting], booked)

    async def no_op(*_args, **_kwargs):
        return None

    monkeypatch.setattr(classes_service, "record_audit", no_op)
    monkeypatch.setattr(classes_service.events, "class_changed", no_op)

    result = await classes_service.cancel_staff_booking(
        session, org_id="org", class_id=class_session.id, booking_id=booked.id, actor_id="owner",
    )

    assert result.status == BookingStatus.CANCELLED
    assert waiting.status == BookingStatus.BOOKED
    assert class_session.booked_count == 1


@pytest.mark.asyncio
async def test_marking_no_show_creates_follow_up_task(monkeypatch):
    class_session = ClassSession(
        organization_id="org", title="Strength", starts_at=now_utc() - timedelta(days=1),
    )
    booking = ClassBooking(
        organization_id="org", class_session_id=class_session.id, member_id="member-1",
        status=BookingStatus.BOOKED,
    )
    member = SimpleNamespace(
        id="member-1", organization_id="org", display_name="Sam", user_id="member-user",
    )
    actor = SimpleNamespace(id="staff-member")

    class NoShowSession:
        def __init__(self):
            self.rows = iter([class_session, actor])
            self.added = []

        async def execute(self, _query):
            return Result(next(self.rows))

        async def get(self, model, _key, **_kwargs):
            return booking if model is ClassBooking else member

        async def flush(self):
            return None

        def add(self, row):
            self.added.append(row)

    session = NoShowSession()
    audits = []

    async def record_audit(*_args, **kwargs):
        audits.append(kwargs)

    notifications = []

    async def create_notification(*_args, **kwargs):
        notifications.append(kwargs)

    async def task_changed(*_args, **_kwargs):
        pass

    monkeypatch.setattr(classes_service, "record_audit", record_audit)
    monkeypatch.setattr(classes_service, "create_notification", create_notification)
    monkeypatch.setattr(classes_service.events, "task_changed", task_changed)
    result = await classes_service.mark_no_show(
        session, org_id="org", class_id=class_session.id, booking_id=booking.id, actor_id="owner",
    )

    task = next(row for row in session.added if isinstance(row, Task))
    assert result.status == BookingStatus.NO_SHOW
    assert task.assignee_member_id == actor.id
    assert "Sam" in task.title and "Strength" in task.description
    assert audits[0]["metadata"]["follow_up_task_id"] == task.id
    assert notifications[0]["recipient_user_id"] == "member-user"
