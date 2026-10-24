"""Daily owner briefing scheduling and duplicate protection."""

from datetime import datetime, timezone

import pytest
from sqlmodel import select

from app.core.constants import Role
from app.models.membership import OrganizationMember
from app.models.notification import Notification
from app.models.organization import Organization
from app.models.user import User
from app.workers import daily_briefing


@pytest.mark.asyncio
async def test_daily_owner_brief_sends_once_per_local_day(db, monkeypatch):
    org = Organization(name="Daily Brief Gym", org_code="DAILY-BRIEF", timezone="Asia/Karachi")
    owner = User(email="brief-owner@example.com", full_name="Brief Owner", hashed_password="unused")
    db.add_all([org, owner])
    await db.flush()
    db.add(OrganizationMember(organization_id=org.id, user_id=owner.id, role=Role.OWNER))
    await db.flush()

    clock = datetime(2026, 10, 24, 4, 15, tzinfo=timezone.utc)
    monkeypatch.setattr(daily_briefing, "now_utc", lambda: clock)
    calls = 0

    async def briefing(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return "Two renewals need attention today."

    monkeypatch.setattr(daily_briefing.workflows, "weekly_briefing", briefing)
    assert await daily_briefing.run_daily_owner_brief(db, org_id=org.id) == {
        "sent": 1, "briefing_date": "2026-10-24",
    }
    assert await daily_briefing.run_daily_owner_brief(db, org_id=org.id) == {
        "sent": 0, "reason": "already_sent",
    }
    notifications = (await db.execute(select(Notification).where(
        Notification.organization_id == org.id,
        Notification.title == "Daily owner brief",
    ))).scalars().all()
    assert len(notifications) == 1
    assert notifications[0].body == "Two renewals need attention today."
    assert calls == 1
