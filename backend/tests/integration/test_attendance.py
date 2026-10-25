"""Integration tests for member check-in / attendance (#18).

Covers: front-desk manual check-in, status-on-check-in flags, today list and
summary, per-member history, idempotent replay, tenant isolation, capability
enforcement, the headline KPI reading attendance (not staff shifts), and the
unification of class attendance into the same behaviour stream.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from sqlmodel import select

from app.core.constants import AttendanceMethod, AttendanceSource, MemberStatus, SubscriptionStatus
from app.core.security import now_utc
from app.models.attendance import Attendance
from app.models.membership import OrganizationMember
from app.models.subscription import Subscription
from app.models.user import User
from tests.helpers import OWNER_PROFILE, latest_code_for

PASSWORD = "Sup3rStr0ng!Pass"
MEMBER_PWD = "M3mberStr0ng!Pwd"


async def _provision_gym(client, *, owner_email="owner@att.com"):
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


async def _signup_member(client, org_code, plan_id, email) -> dict:
    await client.post("/api/v1/memberships/signup/request-email",
                      json={"org_code": org_code, "email": email})
    code = latest_code_for(email)
    await client.post("/api/v1/memberships/signup/verify-email",
                      json={"org_code": org_code, "email": email, "code": code})
    r = await client.post("/api/v1/memberships/signup/set-password",
                          json={"org_code": org_code, "email": email, "password": MEMBER_PWD})
    member_id = r.json()["member_id"]
    r = await client.post("/api/v1/memberships/signup/pay",
                          headers={"Idempotency-Key": str(uuid.uuid4())},
                          json={"org_code": org_code, "email": email, "plan_id": plan_id})
    body = r.json()
    return {"member_id": member_id, "org_id": body["organization_id"], "email": email}


async def _member_headers(client, org_code, email):
    r = await client.post("/api/v1/auth/member-login",
                          json={"org_code": org_code, "email": email, "password": MEMBER_PWD})
    body = r.json()
    return {"Authorization": f"Bearer {body['access_token']}",
            "X-Organization-Id": body["organization_id"]}


async def _provision_front_desk(client, headers, org_code, email="desk@att.com"):
    """Invite + redeem a front-desk user; returns their headers."""

    r = await client.post("/api/v1/staff/invites", headers=headers,
                          json={"role": "front_desk", "email": email})
    invite_code = r.json()["code"]
    r = await client.post("/api/v1/staff/invites/redeem",
                          json={"code": invite_code, "full_name": "Dana Desk", "password": PASSWORD})
    body = r.json()
    return {"Authorization": f"Bearer {body['access_token']}",
            "X-Organization-Id": body["organization_id"]}


# --------------------------------------------------------------- member search
@pytest.mark.asyncio
async def test_front_desk_can_search_members(client):
    """The check-in box must work for front desk, who cannot read /members."""

    headers, _org_id, org_code, plan_id = await _provision_gym(client)
    await _signup_member(client, org_code, plan_id, "findme@att.com")
    desk = await _provision_front_desk(client, headers, org_code)

    # Front desk is blocked from the admin directory...
    assert (await client.get("/api/v1/members", headers=desk)).status_code == 403

    # ...but the attendance search works and finds the member.
    r = await client.get("/api/v1/attendance/members", headers=desk, params={"q": "find"})
    assert r.status_code == 200, r.text
    hits = r.json()
    assert len(hits) == 1
    assert hits[0]["member_email"] == "findme@att.com"

    # Staff are searchable too: the owner ("Alex") can be checked in.
    r = await client.get("/api/v1/attendance/members", headers=desk, params={"q": "owner@att.com"})
    assert r.status_code == 200, r.text
    assert any(h["member_email"] == "owner@att.com" for h in r.json())

    # And front desk can check them in.
    r = await client.post("/api/v1/attendance/check-in", headers=desk,
                          json={"member_id": hits[0]["member_id"], "method": "manual"})
    assert r.status_code == 201, r.text


@pytest.mark.asyncio
async def test_member_search_requires_attendance_capability(client):
    headers, _org_id, org_code, plan_id = await _provision_gym(client)
    member = await _signup_member(client, org_code, plan_id, "nosearch@att.com")
    mh = await _member_headers(client, org_code, member["email"])

    r = await client.get("/api/v1/attendance/members", headers=mh, params={"q": "no"})
    assert r.status_code == 403, r.text


# ------------------------------------------------------------- status card (#19)
async def _force_dues(db, member_id: str, *, price: float = 149.0):
    """Put a member into grace with a renewal owed."""

    m = await db.get(OrganizationMember, member_id)
    m.member_status = MemberStatus.GRACE
    db.add(m)
    sub = (
        await db.execute(select(Subscription).where(Subscription.member_id == member_id))
    ).scalars().first()
    sub.status = SubscriptionStatus.GRACE
    sub.price_snapshot = price
    sub.currency = "USD"
    db.add(sub)
    await db.commit()


@pytest.mark.asyncio
async def test_search_hit_carries_dues_status_card(client, db):
    headers, _org_id, org_code, plan_id = await _provision_gym(client)
    member = await _signup_member(client, org_code, plan_id, "card@att.com")
    await _force_dues(db, member["member_id"])

    r = await client.get("/api/v1/attendance/members", headers=headers, params={"q": "card"})
    assert r.status_code == 200, r.text
    hit = r.json()[0]
    assert hit["member_status"] == "grace"
    assert hit["payment_due"] is True
    assert hit["amount_due"] == 149.0
    assert hit["currency"] == "USD"
    assert hit["hint"] and "Renewal due" in hit["hint"]


@pytest.mark.asyncio
async def test_search_hit_at_risk_hint(client, db):
    headers, org_id, org_code, plan_id = await _provision_gym(client)
    member = await _signup_member(client, org_code, plan_id, "slipping@att.com")

    # An old visit 20 days ago -> at risk, "back after 20 days".
    db.add(Attendance(
        organization_id=org_id,
        member_id=member["member_id"],
        checked_in_at=now_utc() - timedelta(days=20),
        method=AttendanceMethod.MANUAL,
        source=AttendanceSource.FRONT_DESK,
    ))
    await db.commit()

    r = await client.get("/api/v1/attendance/members", headers=headers, params={"q": "slipping"})
    hit = r.json()[0]
    assert hit["at_risk"] is True
    assert hit["days_since_last_visit"] == 20
    assert hit["hint"] == "Back after 20 days — welcome them"


@pytest.mark.asyncio
async def test_search_hit_birthday_hint(client, db):
    headers, _org_id, org_code, plan_id = await _provision_gym(client)
    member = await _signup_member(client, org_code, plan_id, "bday@att.com")

    m = await db.get(OrganizationMember, member["member_id"])
    u = await db.get(User, m.user_id)
    today = now_utc().date()
    u.date_of_birth = today.replace(year=1990)
    db.add(u)
    await db.commit()

    r = await client.get("/api/v1/attendance/members", headers=headers, params={"q": "bday"})
    hit = r.json()[0]
    assert hit["birthday_today"] is True
    assert hit["hint"] == "Birthday today — wish them"


@pytest.mark.asyncio
async def test_expired_member_hint(client, db):
    headers, _org_id, org_code, plan_id = await _provision_gym(client)
    member = await _signup_member(client, org_code, plan_id, "exp@att.com")
    m = await db.get(OrganizationMember, member["member_id"])
    m.member_status = MemberStatus.EXPIRED
    db.add(m)
    await db.commit()

    r = await client.get("/api/v1/attendance/members", headers=headers, params={"q": "exp"})
    hit = r.json()[0]
    assert hit["hint"] == "Membership expired — collect payment"


@pytest.mark.asyncio
async def test_today_feed_carries_status(client, db):
    headers, _org_id, org_code, plan_id = await _provision_gym(client)
    member = await _signup_member(client, org_code, plan_id, "todaycard@att.com")
    await _force_dues(db, member["member_id"])

    await client.post("/api/v1/attendance/check-in", headers=headers,
                      json={"member_id": member["member_id"], "method": "manual"})

    r = await client.get("/api/v1/attendance/today", headers=headers)
    row = r.json()[0]
    assert row["payment_due"] is True
    assert row["amount_due"] == 149.0
    assert row["hint"] and "Renewal due" in row["hint"]


# ------------------------------------------------------------------ check-in
@pytest.mark.asyncio
async def test_check_in_records_visit_and_status(client):
    headers, _org_id, org_code, plan_id = await _provision_gym(client)
    member = await _signup_member(client, org_code, plan_id, "m@att.com")

    r = await client.post("/api/v1/attendance/check-in", headers=headers,
                          json={"member_id": member["member_id"], "method": "manual"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["membership_status"] == "active"
    assert body["payment_due"] is False
    assert body["days_since_last_visit"] is None   # first ever visit
    assert body["visits_today"] == 1
    assert body["member_name"]

    r = await client.get("/api/v1/attendance/today", headers=headers)
    assert r.status_code == 200, r.text
    assert [a["member_id"] for a in r.json()] == [member["member_id"]]

    r = await client.get("/api/v1/attendance/summary", headers=headers)
    assert r.json()["today_count"] == 1
    assert r.json()["unique_today"] == 1

    r = await client.get(f"/api/v1/attendance/members/{member['member_id']}/visits",
                         headers=headers)
    assert r.status_code == 200, r.text
    assert len(r.json()) == 1


@pytest.mark.asyncio
async def test_second_visit_reports_days_since(client):
    headers, _org_id, org_code, plan_id = await _provision_gym(client)
    member = await _signup_member(client, org_code, plan_id, "m2@att.com")

    await client.post("/api/v1/attendance/check-in", headers=headers,
                      json={"member_id": member["member_id"], "method": "manual"})
    # A different method ("qr" vs "manual") is not the same double-tap, so a
    # genuine second visit is recorded.
    r = await client.post("/api/v1/attendance/check-in", headers=headers,
                          json={"member_id": member["member_id"], "method": "qr"},
                          )
    assert r.status_code == 201, r.text
    assert r.json()["days_since_last_visit"] == 0
    assert r.json()["visits_today"] == 2
    assert r.json()["method"] == "qr"


@pytest.mark.asyncio
async def test_check_in_is_idempotent(client):
    headers, _org_id, org_code, plan_id = await _provision_gym(client)
    member = await _signup_member(client, org_code, plan_id, "m3@att.com")

    key = str(uuid.uuid4())
    h = {**headers, "Idempotency-Key": key}
    r1 = await client.post("/api/v1/attendance/check-in", headers=h,
                           json={"member_id": member["member_id"], "method": "manual"})
    r2 = await client.post("/api/v1/attendance/check-in", headers=h,
                           json={"member_id": member["member_id"], "method": "manual"})
    assert r1.status_code == 201 and r2.status_code == 201, (r1.text, r2.text)
    assert r1.json()["id"] == r2.json()["id"]

    r = await client.get("/api/v1/attendance/today", headers=headers)
    assert len(r.json()) == 1


@pytest.mark.asyncio
async def test_check_in_is_tenant_isolated(client):
    headers_a, _org_a, code_a, plan_a = await _provision_gym(client, owner_email="a@att.com")
    member = await _signup_member(client, code_a, plan_a, "iso@att.com")

    headers_b, *_ = await _provision_gym(client, owner_email="b@att.com")
    r = await client.post("/api/v1/attendance/check-in", headers=headers_b,
                          json={"member_id": member["member_id"], "method": "manual"})
    assert r.status_code == 404, r.text


@pytest.mark.asyncio
async def test_member_cannot_check_in(client):
    headers, _org_id, org_code, plan_id = await _provision_gym(client)
    member = await _signup_member(client, org_code, plan_id, "noperm@att.com")
    mh = await _member_headers(client, org_code, member["email"])

    r = await client.post("/api/v1/attendance/check-in", headers=mh,
                          json={"member_id": member["member_id"], "method": "manual"})
    assert r.status_code == 403, r.text


# ------------------------------------------------------------------- headline
@pytest.mark.asyncio
async def test_headline_check_ins_are_member_visits(client):
    headers, _org_id, org_code, plan_id = await _provision_gym(client)
    member = await _signup_member(client, org_code, plan_id, "head@att.com")

    r = await client.get("/api/v1/analytics/headline", headers=headers)
    assert r.json()["today_check_ins"] == 0

    await client.post("/api/v1/attendance/check-in", headers=headers,
                      json={"member_id": member["member_id"], "method": "manual"})

    r = await client.get("/api/v1/analytics/headline", headers=headers)
    assert r.json()["today_check_ins"] == 1
    assert r.json()["members_slipping"] == 0


# ------------------------------------------------------------- class unify
@pytest.mark.asyncio
async def test_class_attendance_unifies_into_visit(client):
    headers, _org_id, org_code, plan_id = await _provision_gym(client)
    member = await _signup_member(client, org_code, plan_id, "class@att.com")
    mh = await _member_headers(client, org_code, member["email"])

    r = await client.post("/api/v1/classes", headers=headers,
                          json={"title": "Boxing 101", "starts_at": "2026-10-05T10:00:00"})
    assert r.status_code == 201, r.text
    class_id = r.json()["id"]

    r = await client.post("/api/v1/classes/book", headers={**mh, "Idempotency-Key": str(uuid.uuid4())},
                          json={"class_session_id": class_id})
    assert r.status_code == 200, r.text

    r = await client.get(f"/api/v1/classes/{class_id}/bookings", headers=headers)
    booking_id = r.json()[0]["booking_id"]

    r = await client.post(f"/api/v1/classes/{class_id}/bookings/{booking_id}/attend",
                          headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "attended"

    # The class visit shows up in the member's attendance history, source=class.
    r = await client.get(f"/api/v1/attendance/members/{member['member_id']}/visits",
                         headers=headers)
    assert len(r.json()) == 1
    assert r.json()[0]["source"] == "class"
    assert r.json()[0]["class_session_id"] == class_id


@pytest.mark.asyncio
async def test_class_waitlist_promotes_on_cancellation_and_staff_can_mark_no_show(client, monkeypatch):
    from app.services import organizations_service
    from app.integrations.stripe_connect import connect_stripe

    monkeypatch.setattr(organizations_service.platform_stripe, "live", False)
    monkeypatch.setattr(connect_stripe, "live", False)
    headers, _org_id, org_code, plan_id = await _provision_gym(client)
    first = await _signup_member(client, org_code, plan_id, "waitlist1@att.com")
    second = await _signup_member(client, org_code, plan_id, "waitlist2@att.com")
    starts_at = (now_utc() + timedelta(days=1)).isoformat()
    r = await client.post("/api/v1/classes", headers=headers, json={
        "title": "Full class", "starts_at": starts_at, "capacity": 1,
    })
    assert r.status_code == 201, r.text
    class_id = r.json()["id"]

    first_headers = await _member_headers(client, org_code, first["email"])
    booked = await client.post("/api/v1/classes/book", headers={
        **first_headers, "Idempotency-Key": str(uuid.uuid4()),
    }, json={"class_session_id": class_id})
    assert booked.status_code == 200, booked.text
    queued = await client.post(f"/api/v1/classes/{class_id}/waitlist", headers=headers,
                               json={"member_id": second["member_id"]})
    assert queued.status_code == 201, queued.text
    assert queued.json()["status"] == "waitlisted"

    cancelled = await client.delete(f"/api/v1/classes/bookings/{booked.json()['id']}", headers=first_headers)
    assert cancelled.status_code == 200, cancelled.text
    bookings = (await client.get(f"/api/v1/classes/{class_id}/bookings", headers=headers)).json()
    assert next(row for row in bookings if row["member_id"] == second["member_id"])["status"] == "booked"

    staff_cancel_class = await client.post("/api/v1/classes", headers=headers, json={
        "title": "Staff cancellation", "starts_at": starts_at, "capacity": 1,
    })
    second_booking = await client.post("/api/v1/classes/book", headers={
        **(await _member_headers(client, org_code, second["email"])), "Idempotency-Key": str(uuid.uuid4()),
    }, json={"class_session_id": staff_cancel_class.json()["id"]})
    staff_waitlist = await client.post(
        f"/api/v1/classes/{staff_cancel_class.json()['id']}/waitlist", headers=headers,
        json={"member_id": first["member_id"]},
    )
    assert staff_waitlist.json()["status"] == "waitlisted"
    staff_cancel = await client.post(
        f"/api/v1/classes/{staff_cancel_class.json()['id']}/bookings/{second_booking.json()['id']}/cancel",
        headers=headers,
    )
    assert staff_cancel.status_code == 200, staff_cancel.text
    staff_bookings = (await client.get(
        f"/api/v1/classes/{staff_cancel_class.json()['id']}/bookings", headers=headers,
    )).json()
    assert next(row for row in staff_bookings if row["member_id"] == first["member_id"])["status"] == "booked"

    past = await client.post("/api/v1/classes", headers=headers, json={
        "title": "Completed class", "starts_at": (now_utc() - timedelta(days=1)).isoformat(),
        "capacity": 1,
    })
    assert past.status_code == 201, past.text
    second_headers = await _member_headers(client, org_code, second["email"])
    past_booking = await client.post("/api/v1/classes/book", headers={
        **second_headers, "Idempotency-Key": str(uuid.uuid4()),
    }, json={"class_session_id": past.json()["id"]})
    assert past_booking.status_code == 200, past_booking.text
    no_show = await client.post(
        f"/api/v1/classes/{past.json()['id']}/bookings/{past_booking.json()['id']}/no-show",
        headers=headers,
    )
    assert no_show.status_code == 200, no_show.text
    assert no_show.json()["status"] == "no_show"
    tasks = await client.get("/api/v1/staff/tasks", headers=headers)
    assert tasks.status_code == 200, tasks.text
    assert any("missed class" in task["title"] for task in tasks.json())


# ------------------------------------------------------------- offline (#23)
@pytest.mark.asyncio
async def test_roster_lists_everyone(client):
    headers, _org_id, org_code, plan_id = await _provision_gym(client)
    await _signup_member(client, org_code, plan_id, "roster@att.com")
    r = await client.get("/api/v1/attendance/roster", headers=headers)
    assert r.status_code == 200, r.text
    assert any(x["member_email"] == "roster@att.com" for x in r.json())


@pytest.mark.asyncio
async def test_sync_batch_idempotent_and_honors_time(client):
    headers, _org_id, org_code, plan_id = await _provision_gym(client)
    member = await _signup_member(client, org_code, plan_id, "sync@att.com")
    key = str(uuid.uuid4())
    items = [{
        "id": "c1", "member_id": member["member_id"], "method": "manual",
        "checked_in_at": "2026-10-01T09:30:00", "idempotency_key": key,
    }]

    r = await client.post("/api/v1/attendance/sync", headers=headers, json={"items": items})
    assert r.status_code == 200, r.text
    assert r.json()["results"][0]["status"] == "synced"

    # Replaying the same key does not create a second visit.
    r2 = await client.post("/api/v1/attendance/sync", headers=headers, json={"items": items})
    assert r2.json()["results"][0]["status"] == "synced"

    r = await client.get(f"/api/v1/attendance/members/{member['member_id']}/visits", headers=headers)
    assert len(r.json()) == 1
    assert r.json()[0]["checked_in_at"].startswith("2026-10-01T09:30")


@pytest.mark.asyncio
async def test_sync_reports_bad_item_without_failing_batch(client):
    headers, _org_id, org_code, plan_id = await _provision_gym(client)
    member = await _signup_member(client, org_code, plan_id, "ok@att.com")
    items = [
        {"id": "good", "member_id": member["member_id"], "idempotency_key": str(uuid.uuid4())},
        {"id": "bad", "member_id": "does-not-exist", "idempotency_key": str(uuid.uuid4())},
    ]
    r = await client.post("/api/v1/attendance/sync", headers=headers, json={"items": items})
    assert r.status_code == 200, r.text
    by_id = {x["id"]: x for x in r.json()["results"]}
    assert by_id["good"]["status"] == "synced"
    assert by_id["bad"]["status"] == "error"
