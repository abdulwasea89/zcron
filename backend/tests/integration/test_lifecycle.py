"""Integration tests for celebrations + win-back (#36)."""

from __future__ import annotations

import uuid
from datetime import date, datetime

import pytest
from sqlmodel import select

from app.core.constants import AttendanceMethod, AttendanceSource, MemberStatus, SubscriptionStatus
from app.core.security import now_utc
from app.integrations.email import outbox
from app.models.attendance import Attendance
from app.models.celebration import MemberCelebration
from app.models.membership import OrganizationMember
from app.models.subscription import Subscription
from app.models.user import User
from app.services import celebrations_service as celebrations
from app.services import winback_service as winback
from tests.helpers import OWNER_PROFILE, latest_code_for

PASSWORD = "Sup3rStr0ng!Pass"
MEMBER_PWD = "M3mberStr0ng!Pwd"


async def _provision_gym(client, *, owner_email="owner@cel.com"):
    await client.post("/api/v1/auth/register", json={
        "full_name": "Alex", "email": owner_email,
        "password": PASSWORD, "confirm_password": PASSWORD, **OWNER_PROFILE})
    code = latest_code_for(owner_email)
    await client.post("/api/v1/auth/verify-email", json={"email": owner_email, "code": code})
    r = await client.post("/api/v1/organizations/register", json={
        "owner_email": owner_email,
        "details": {"name": "Iron Pulse Boxing", "default_currency": "USD"},
        "tier": "pro"})
    body = r.json()
    org_id = body["organization"]["id"]
    org_code = body["organization"]["org_code"]
    headers = {"Authorization": f"Bearer {body['access_token']}", "X-Organization-Id": org_id}
    await client.post("/api/v1/organizations/me/connect", headers=headers)
    await client.post("/api/v1/organizations/me/connect/complete", headers=headers)
    r = await client.post("/api/v1/plans", headers=headers, json={
        "name": "Monthly", "price": 149.0, "billing_type": "recurring",
        "cycle_unit": "month", "cycle_length": 1})
    plan_id = r.json()["id"]
    await client.post(f"/api/v1/plans/{plan_id}/publish", headers=headers)
    return headers, org_id, org_code, plan_id


async def _signup_member(client, org_code, plan_id, email) -> str:
    await client.post("/api/v1/memberships/signup/request-email",
                      json={"org_code": org_code, "email": email})
    code = latest_code_for(email)
    await client.post("/api/v1/memberships/signup/verify-email",
                      json={"org_code": org_code, "email": email, "code": code})
    r = await client.post("/api/v1/memberships/signup/set-password",
                          json={"org_code": org_code, "email": email, "password": MEMBER_PWD})
    member_id = r.json()["member_id"]
    await client.post("/api/v1/memberships/signup/pay",
                      headers={"Idempotency-Key": str(uuid.uuid4())},
                      json={"org_code": org_code, "email": email, "plan_id": plan_id})
    return member_id


async def _set_dob_today(db, member_id):
    member = await db.get(OrganizationMember, member_id)
    user = await db.get(User, member.user_id)
    today = now_utc().date()          # same clock the service uses (UTC)
    user.date_of_birth = date(1992, today.month, today.day)
    db.add(user)
    await db.commit()


async def _add_visits(db, org_id, member_id, n):
    for _ in range(n):
        db.add(Attendance(organization_id=org_id, member_id=member_id,
                          checked_in_at=now_utc(), method=AttendanceMethod.MANUAL,
                          source=AttendanceSource.SYSTEM))
    await db.commit()


async def _expire(db, member_id):
    member = await db.get(OrganizationMember, member_id)
    member.member_status = MemberStatus.EXPIRED
    db.add(member)
    sub = (await db.execute(
        select(Subscription).where(Subscription.member_id == member_id))).scalar_one()
    sub.status = SubscriptionStatus.EXPIRED
    db.add(sub)
    await db.commit()


# -------------------------------------------------------------- celebrations
@pytest.mark.asyncio
async def test_birthday_celebrated_once(client, db):
    _h, org_id, org_code, plan_id = await _provision_gym(client)
    member_id = await _signup_member(client, org_code, plan_id, "bday@cel.com")
    await _set_dob_today(db, member_id)
    outbox.clear()

    r = await celebrations.run_sweep(db, org_id=org_id)
    await db.commit()
    assert r["birthdays"] == 1
    assert any("birthday" in m.subject.lower() for m in outbox)

    # Second run on the same day is a no-op.
    r = await celebrations.run_sweep(db, org_id=org_id)
    await db.commit()
    assert r["birthdays"] == 0
    rows = (await db.execute(
        select(MemberCelebration).where(
            MemberCelebration.member_id == member_id,
            MemberCelebration.kind == "birthday")
    )).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_visit_milestone_only_top_emailed(client, db):
    _h, org_id, org_code, plan_id = await _provision_gym(client)
    member_id = await _signup_member(client, org_code, plan_id, "milestone@cel.com")
    await _add_visits(db, org_id, member_id, 120)
    outbox.clear()

    await celebrations.run_sweep(db, org_id=org_id)
    await db.commit()

    rows = (await db.execute(
        select(MemberCelebration).where(
            MemberCelebration.member_id == member_id,
            MemberCelebration.kind == "visits")
    )).scalars().all()
    assert sorted(int(r.key) for r in rows) == [10, 50, 100]
    # Only the highest crossed milestone emails.
    assert sum(1 for m in outbox if m.to == "milestone@cel.com") == 1


@pytest.mark.asyncio
async def test_anniversary_and_upcoming(client, db):
    _h, org_id, org_code, plan_id = await _provision_gym(client)
    member_id = await _signup_member(client, org_code, plan_id, "anniv@cel.com")
    member = await db.get(OrganizationMember, member_id)
    now = now_utc()
    member.joined_at = datetime(now.year - 1, now.month, now.day)
    db.add(member)
    await db.commit()

    r = await celebrations.run_sweep(db, org_id=org_id)
    await db.commit()
    assert r["anniversaries"] == 1

    up = await celebrations.upcoming(db, org_id=org_id, days=5)
    assert any(u["member_id"] == member_id and u["kind"] == "anniversary" for u in up)


# ------------------------------------------------------------------ win-back
@pytest.mark.asyncio
async def test_win_back_campaign_cooldown_and_recovery(client, db, monkeypatch):
    async def delivered(*args, **kwargs):
        return True

    monkeypatch.setattr(winback, "send_email", delivered)
    headers, org_id, org_code, plan_id = await _provision_gym(client)
    member_id = await _signup_member(client, org_code, plan_id, "lost@cel.com")
    await _expire(db, member_id)
    lapsed = await winback.lapsed_members(db, org_id=org_id)
    assert next(row for row in lapsed if row["member_id"] == member_id)["can_contact"] is False
    member = await db.get(OrganizationMember, member_id)
    member.marketing_email_consent = True
    db.add(member)
    await db.commit()
    lapsed = await winback.lapsed_members(db, org_id=org_id)
    assert next(row for row in lapsed if row["member_id"] == member_id)["can_contact"] is True

    r = await winback.run_campaign(db, org_id=org_id, actor_user_id="u1")
    await db.commit()
    assert r["sent"] == 1

    # Cooldown: a second run the same day sends nothing.
    r = await winback.run_campaign(db, org_id=org_id, actor_user_id="u1")
    await db.commit()
    assert r["sent"] == 0

    # Reactivation (here via cash log) resolves the open win-back.
    r = await client.post("/api/v1/cash/log", headers={**headers, "Idempotency-Key": "winback-reactivation"}, json={
        "member_id": member_id, "plan_id": plan_id, "amount": 149.0, "method": "cash"})
    assert r.status_code == 201, r.text

    s = await winback.summary(db, org_id=org_id)
    assert s["recovered"] == 1
    assert s["recovered_revenue"] == 149.0


@pytest.mark.asyncio
async def test_win_back_api_capability(client, db):
    headers, org_id, org_code, plan_id = await _provision_gym(client)
    member_id = await _signup_member(client, org_code, plan_id, "lost@cel.com")
    await _expire(db, member_id)

    r = await client.get("/api/v1/win-back/lapsed", headers=headers)
    assert r.status_code == 200, r.text
    assert any(row["member_id"] == member_id for row in r.json())

    r = await client.post("/api/v1/win-back/campaign", headers=headers, json={})
    assert r.status_code == 200, r.text
    assert r.json()["sent"] == 0
    member = await db.get(OrganizationMember, member_id)
    member.marketing_in_app_consent = True
    db.add(member)
    await db.commit()
    r = await client.post("/api/v1/win-back/campaign", headers=headers, json={})
    assert r.status_code == 200, r.text
    assert r.json()["sent"] == 1

    # Front desk cannot access retention surfaces.
    r = await client.post("/api/v1/staff/invites", headers=headers,
                          json={"role": "front_desk", "email": "desk@cel.com"})
    invite = r.json()["code"]
    r = await client.post("/api/v1/staff/invites/redeem",
                          json={"code": invite, "full_name": "Dana", "password": PASSWORD})
    desk = {"Authorization": f"Bearer {r.json()['access_token']}",
            "X-Organization-Id": r.json()["organization_id"]}
    assert (await client.get("/api/v1/win-back/lapsed", headers=desk)).status_code == 403
    assert (await client.get("/api/v1/celebrations/upcoming", headers=desk)).status_code == 403
