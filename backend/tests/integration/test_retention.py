"""Integration tests for retention: attendance-drop (#33) and churn score (#34)."""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from sqlmodel import select

from app.core.constants import (
    AttendanceMethod, AttendanceSource, MemberStatus, PaymentKind, PaymentMethod,
    PaymentStatus, SubscriptionStatus,
)
from app.core.security import now_utc
from app.models.attendance import Attendance
from app.models.membership import OrganizationMember
from app.models.payment import Payment
from app.models.staff import Task
from app.models.subscription import Subscription
from app.services import retention_service as retention
from app.services.recurring_billing_service import complete_recurring_renewal
from app.workers.retention import run_retention_sweep
from tests.helpers import OWNER_PROFILE, latest_code_for

PASSWORD = "Sup3rStr0ng!Pass"
MEMBER_PWD = "M3mberStr0ng!Pwd"

# 8 visits spread across the prior 8 weeks (days 30..44 ago), none recent.
_BASELINE_ONLY = [30, 32, 34, 36, 38, 40, 42, 44]


async def _provision_gym(client, *, owner_email="owner@ret.com"):
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


async def _add_visits(db, org_id, member_id, days_ago):
    for d in days_ago:
        db.add(Attendance(
            organization_id=org_id, member_id=member_id,
            checked_in_at=now_utc() - timedelta(days=d),
            method=AttendanceMethod.MANUAL, source=AttendanceSource.SYSTEM))
    await db.commit()


async def _set_tenure(db, member_id, *, days_ago):
    member = await db.get(OrganizationMember, member_id)
    member.joined_at = now_utc() - timedelta(days=days_ago)
    db.add(member)
    await db.commit()


# --------------------------------------------------------------------- #33
@pytest.mark.asyncio
async def test_attendance_drop_vs_own_baseline(client, db):
    _h, org_id, org_code, plan_id = await _provision_gym(client)
    member_id = await _signup_member(client, org_code, plan_id, "drop@ret.com")
    await _set_tenure(db, member_id, days_ago=100)
    await _add_visits(db, org_id, member_id, _BASELINE_ONLY)

    risk = await retention.member_risk(db, org_id=org_id, member_id=member_id)
    assert risk.trend.eligible is True
    assert risk.trend.is_drop is True
    assert risk.trend.severity == "silent"        # baseline existed, now zero
    assert risk.trend.drop_ratio == 0.0
    assert any(r.code == "attendance_drop" for r in risk.reasons)

    # The drop list surfaces the member.
    drops = await retention.attendance_drops(db, org_id=org_id)
    assert any(r.member_id == member_id for r in drops)


@pytest.mark.asyncio
async def test_no_drop_when_consistent(client, db):
    _h, org_id, org_code, plan_id = await _provision_gym(client)
    member_id = await _signup_member(client, org_code, plan_id, "steady@ret.com")
    await _set_tenure(db, member_id, days_ago=100)
    await _add_visits(db, org_id, member_id, _BASELINE_ONLY)
    await _add_visits(db, org_id, member_id, [2, 4, 6, 8, 10, 12])  # recent, consistent

    risk = await retention.member_risk(db, org_id=org_id, member_id=member_id)
    assert risk.trend.is_drop is False
    assert risk.band == "low"


# --------------------------------------------------------------------- #34
@pytest.mark.asyncio
async def test_churn_score_with_reasons_and_band(client, db):
    _h, org_id, org_code, plan_id = await _provision_gym(client)
    member_id = await _signup_member(client, org_code, plan_id, "risk@ret.com")
    await _set_tenure(db, member_id, days_ago=100)
    await _add_visits(db, org_id, member_id, _BASELINE_ONLY)

    # Expire them too: drop (silent) + dormancy (30d) + expired = 100.
    member = await db.get(OrganizationMember, member_id)
    member.member_status = MemberStatus.EXPIRED
    db.add(member)
    sub = (await db.execute(
        select(Subscription).where(Subscription.member_id == member_id)
    )).scalar_one()
    sub.status = SubscriptionStatus.EXPIRED
    db.add(sub)
    await db.commit()

    risk = await retention.member_risk(db, org_id=org_id, member_id=member_id)
    assert risk.score == 100
    assert risk.band == "high"
    codes = {r.code for r in risk.reasons}
    assert {"attendance_drop", "dormant_30", "expired"} <= codes
    # Every reason is human-readable.
    assert all(r.label for r in risk.reasons)


@pytest.mark.asyncio
async def test_retention_summary_counts_revenue_at_risk(client, db):
    _h, org_id, org_code, plan_id = await _provision_gym(client)
    member_id = await _signup_member(client, org_code, plan_id, "rev@ret.com")
    other_member_id = await _signup_member(client, org_code, plan_id, "rev-pkr@ret.com")
    await _set_tenure(db, member_id, days_ago=100)
    await _set_tenure(db, other_member_id, days_ago=100)
    await _add_visits(db, org_id, member_id, _BASELINE_ONLY)
    await _add_visits(db, org_id, other_member_id, _BASELINE_ONLY)
    member = await db.get(OrganizationMember, member_id)
    member.member_status = MemberStatus.EXPIRED
    other_member = await db.get(OrganizationMember, other_member_id)
    other_member.member_status = MemberStatus.EXPIRED
    other_subscription = (await db.execute(select(Subscription).where(
        Subscription.organization_id == org_id,
        Subscription.member_id == other_member_id,
    ))).scalars().first()
    other_subscription.currency = "PKR"
    db.add_all([member, other_member, other_subscription])
    await db.commit()

    summary = await retention.retention_summary(db, org_id=org_id)
    assert summary["high"] >= 1
    assert summary["revenue_at_risk"] == 149.0
    assert summary["revenue_at_risk_by_currency"] == {"PKR": 149.0, "USD": 149.0}


@pytest.mark.asyncio
async def test_recovered_renewal_appears_in_tenant_scoped_wins_feed(client, db, monkeypatch):
    from app.services import organizations_service

    monkeypatch.setattr(organizations_service.platform_stripe, "live", False)
    monkeypatch.setattr(organizations_service.connect_stripe, "live", False)
    headers, org_id, org_code, plan_id = await _provision_gym(client)
    member_id = await _signup_member(client, org_code, plan_id, "recovered@ret.com")
    lead_response = await client.post(
        "/api/v1/leads", headers={**headers, "Idempotency-Key": "source-lead"},
        json={"name": "Recovered Prospect", "email": "recovered@ret.com", "source": "whatsapp"},
    )
    assert lead_response.status_code == 201, lead_response.text
    lead_id = lead_response.json()["id"]
    joined = await client.patch(
        f"/api/v1/leads/{lead_id}", headers={**headers, "Idempotency-Key": "source-lead-joined"},
        json={"stage": "joined"},
    )
    assert joined.status_code == 200, joined.text
    member = await db.get(OrganizationMember, member_id)
    sub = (await db.execute(
        select(Subscription).where(Subscription.member_id == member_id)
    )).scalar_one()
    sub.status = SubscriptionStatus.GRACE
    member.member_status = MemberStatus.GRACE
    payment = Payment(
        organization_id=org_id, member_id=member_id, subscription_id=sub.id, plan_id=plan_id,
        kind=PaymentKind.MEMBER_FEE, method=PaymentMethod.CARD, status=PaymentStatus.SUCCEEDED,
        amount=149.0, currency="USD",
        note=f"member_renewal:{sub.id}:{sub.current_period_end.isoformat()}:2:123",
    )
    db.add_all([sub, member, payment])
    await db.flush()

    assert await complete_recurring_renewal(db, payment)
    await db.commit()

    response = await client.get("/api/v1/retention/wins", headers=headers)
    assert response.status_code == 200, response.text
    wins = response.json()
    assert len(wins) == 2
    recovery = next(win for win in wins if win["kind"] == "renewal_recovered")
    conversion = next(win for win in wins if win["kind"] == "lead_converted")
    assert recovery["payment_id"] == payment.id
    assert recovery["member_id"] == member_id
    assert recovery["amount"] == 149.0
    assert recovery["lead_source"] == "whatsapp"
    assert conversion["lead_id"] == lead_id
    assert conversion["member_id"] == member_id
    assert conversion["member_name"]
    assert conversion["amount"] is None
    assert conversion["lead_source"] == "whatsapp"

    other_headers, *_ = await _provision_gym(client, owner_email="other-wins@ret.com")
    response = await client.get("/api/v1/retention/wins", headers=other_headers)
    assert response.status_code == 200 and response.json() == []


# --------------------------------------------------------------------- worker
@pytest.mark.asyncio
async def test_worker_opens_one_task_per_high_risk(client, db):
    _h, org_id, org_code, plan_id = await _provision_gym(client)
    member_id = await _signup_member(client, org_code, plan_id, "task@ret.com")
    await _set_tenure(db, member_id, days_ago=100)
    await _add_visits(db, org_id, member_id, _BASELINE_ONLY)
    member = await db.get(OrganizationMember, member_id)
    member.member_status = MemberStatus.EXPIRED
    db.add(member)
    await db.commit()

    await run_retention_sweep(db, org_id=org_id)
    await db.commit()
    await run_retention_sweep(db, org_id=org_id)  # dedup: no second task
    await db.commit()

    tasks = (await db.execute(
        select(Task).where(Task.organization_id == org_id, Task.title.like("[Retention]%"))
    )).scalars().all()
    assert len(tasks) == 1
    assert f"[mid:{member_id}]" in (tasks[0].description or "")


# ----------------------------------------------------------------------- API
@pytest.mark.asyncio
async def test_retention_api_capability_and_isolation(client, db, monkeypatch):
    from app.services import organizations_service

    monkeypatch.setattr(organizations_service.platform_stripe, "live", False)
    monkeypatch.setattr(organizations_service.connect_stripe, "live", False)
    headers, org_id, org_code, plan_id = await _provision_gym(client)
    member_id = await _signup_member(client, org_code, plan_id, "api@ret.com")
    member = await db.get(OrganizationMember, member_id)
    member.phone = "+15551234567"
    db.add(member)
    await _set_tenure(db, member_id, days_ago=100)
    await _add_visits(db, org_id, member_id, _BASELINE_ONLY)

    r = await client.get("/api/v1/retention/at-risk", headers=headers)
    assert r.status_code == 200, r.text
    assert any(row["member_id"] == member_id for row in r.json())
    assert next(row for row in r.json() if row["member_id"] == member_id)["phone"] == "+15551234567"

    r = await client.get(f"/api/v1/retention/members/{member_id}", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["trend"]["is_drop"] is True

    # A second org cannot read the first org's member.
    _h2, _org2, _c2, _p2 = await _provision_gym(client, owner_email="other@ret.com")
    assert (await client.get(f"/api/v1/retention/members/{member_id}", headers=_h2)).status_code == 404

    # Front desk lacks VIEW_RETENTION.
    r = await client.post("/api/v1/staff/invites", headers=headers,
                          json={"role": "front_desk", "email": "desk@ret.com"})
    invite = r.json()["code"]
    r = await client.post("/api/v1/staff/invites/redeem",
                          json={"code": invite, "full_name": "Dana", "password": PASSWORD})
    desk = {"Authorization": f"Bearer {r.json()['access_token']}",
            "X-Organization-Id": r.json()["organization_id"]}
    assert (await client.get("/api/v1/retention/at-risk", headers=desk)).status_code == 403
