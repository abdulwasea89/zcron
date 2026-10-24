from datetime import timedelta
import pytest

from app.core.constants import BookingStatus
from app.core.security import now_utc
from app.models.class_session import ClassBooking, ClassSession
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

    async def get(self, _model, _key):
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
