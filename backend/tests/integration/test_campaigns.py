"""Integration tests for segmented campaigns by channel (#39)."""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.core.constants import CampaignDeliveryStatus, NotificationKind
from app.core.security import now_utc
from app.models.attendance import Attendance
from app.models.campaign import Campaign, CampaignDelivery
from app.models.membership import OrganizationMember
from app.models.notification import Notification
from app.models.user import User
from app.workers.campaigns import run_due_campaigns
from tests.helpers import OWNER_PROFILE, latest_code_for

PASSWORD = "Sup3rStr0ng!Pass"
MEMBER_PWD = "M3mberStr0ng!Pwd"


@pytest.fixture(autouse=True)
def disable_external_stripe(monkeypatch):
    from app.services import organizations_service
    from app.services import campaign_service
    from app.integrations.email import EmailSendResult

    async def accepted_email(*_args, **_kwargs):
        return EmailSendResult(True, str(uuid.uuid4()))

    monkeypatch.setattr(campaign_service, "send_campaign_email", accepted_email)

    monkeypatch.setattr(organizations_service.platform_stripe, "live", False)
    monkeypatch.setattr(organizations_service.connect_stripe, "live", False)


async def _provision_gym(client, *, owner_email="owner@camp.com"):
    await client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Alex",
            "email": owner_email,
            "password": PASSWORD,
            "confirm_password": PASSWORD,
            **OWNER_PROFILE,
        },
    )
    code = latest_code_for(owner_email)
    await client.post("/api/v1/auth/verify-email", json={"email": owner_email, "code": code})
    r = await client.post(
        "/api/v1/organizations/register",
        json={
            "owner_email": owner_email,
            "details": {"name": "Iron Pulse Boxing", "default_currency": "USD"},
            "tier": "pro",
        },
    )
    body = r.json()
    org_id = body["organization"]["id"]
    org_code = body["organization"]["org_code"]
    headers = {"Authorization": f"Bearer {body['access_token']}", "X-Organization-Id": org_id}
    await client.post("/api/v1/organizations/me/connect", headers=headers)
    await client.post("/api/v1/organizations/me/connect/complete", headers=headers)
    r = await client.post(
        "/api/v1/plans",
        headers=headers,
        json={
            "name": "Monthly",
            "price": 149.0,
            "billing_type": "recurring",
            "cycle_unit": "month",
            "cycle_length": 1,
        },
    )
    plan_id = r.json()["id"]
    await client.post(f"/api/v1/plans/{plan_id}/publish", headers=headers)
    return headers, org_id, org_code, plan_id


async def _signup_member(client, org_code, plan_id, headers, email, *, marketing_consent=True) -> str:
    await client.post(
        "/api/v1/memberships/signup/request-email", json={"org_code": org_code, "email": email}
    )
    code = latest_code_for(email)
    await client.post(
        "/api/v1/memberships/signup/verify-email",
        json={"org_code": org_code, "email": email, "code": code},
    )
    r = await client.post(
        "/api/v1/memberships/signup/set-password",
        json={"org_code": org_code, "email": email, "password": MEMBER_PWD},
    )
    member_id = r.json()["member_id"]
    await client.post(
        "/api/v1/memberships/signup/pay",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"org_code": org_code, "email": email, "plan_id": plan_id},
    )
    if marketing_consent:
        consent = await client.put(
            f"/api/v1/privacy/members/{member_id}/consent",
            headers={**headers, "Idempotency-Key": f"campaign-consent-{member_id}"},
            json={"email": True, "sms": False, "in_app": True},
        )
        assert consent.status_code == 200, consent.text
    return member_id


async def _create_campaign(client, headers, **kw):
    r = await client.post(
        "/api/v1/campaigns",
        headers=headers,
        json={
            "title": kw.get("title", "Summer Blast"),
            "subject": kw.get("subject", "Limited offer for you"),
            "body": kw.get("body", "Come back and save 20% this week."),
            "channel": kw.get("channel", "in_app"),
            "member_status": kw.get("member_status"),
            "min_days_since_last_visit": kw.get("min_days_since_last_visit"),
            "send_limit": kw.get("send_limit", 200),
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


# ------------------------------------------------------------------- send flows
@pytest.mark.asyncio
async def test_campaign_sends_to_active_segment_and_dedups(client, db):
    headers, org_id, org_code, plan_id = await _provision_gym(client)
    await _signup_member(client, org_code, plan_id, headers, "alice@camp.com")
    await _signup_member(client, org_code, plan_id, headers, "bob@camp.com")

    campaign = await _create_campaign(client, headers, channel="in_app")
    assert campaign["status"] == "draft"

    r = await client.post(f"/api/v1/campaigns/{campaign['id']}/send", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["targeted"] == 2
    assert body["sent"] == 2
    assert body["suppressed"] == 0
    assert body["failed"] == 0

    deliveries = (
        (
            await db.execute(
                select(CampaignDelivery).where(CampaignDelivery.organization_id == org_id)
            )
        )
        .scalars()
        .all()
    )
    assert len(deliveries) == 2
    assert all(d.status == CampaignDeliveryStatus.SENT for d in deliveries)

    # In-app notifications of kind CAMPAIGN were created.
    notifs = (
        (
            await db.execute(
                select(Notification).where(
                    Notification.organization_id == org_id,
                    Notification.category == NotificationKind.CAMPAIGN,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(notifs) == 2
    assert notifs[0].title == "Limited offer for you"

    # Re-sending a sent campaign is rejected — no double-delivery possible.
    r = await client.post(f"/api/v1/campaigns/{campaign['id']}/send", headers=headers)
    assert r.status_code == 409
    assert r.json()["detail"] == "Cannot send a 'sent' campaign."
    all_deliveries = (await db.execute(select(CampaignDelivery))).scalars().all()
    assert len(all_deliveries) == 2
    # No duplicate notifications regardless.
    notifs2 = (
        (
            await db.execute(
                select(Notification).where(
                    Notification.organization_id == org_id,
                    Notification.category == NotificationKind.CAMPAIGN,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(notifs2) == 2

    db_campaign = await db.get(Campaign, campaign["id"])
    assert db_campaign.status.value == "sent"
    assert db_campaign.sent_count == 2


@pytest.mark.asyncio
async def test_email_channel_suppresses_unverified_addresses(client, db):
    headers, org_id, org_code, plan_id = await _provision_gym(client)
    member_id = await _signup_member(client, org_code, plan_id, headers, "anon@camp.com")

    # Signup verified the address; flip it back to simulate an imported member
    # whose email was never confirmed (Security Rule #6 — no email without it).
    member = await db.get(OrganizationMember, member_id)
    user = await db.get(User, member.user_id)
    user.email_verified = False
    await db.commit()

    campaign = await _create_campaign(client, headers, channel="email")
    r = await client.post(f"/api/v1/campaigns/{campaign['id']}/send", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["targeted"] == 1
    assert r.json()["sent"] == 0  # email not verified -> suppressed
    assert r.json()["suppressed"] == 1

    delivery = (
        await db.execute(select(CampaignDelivery).where(CampaignDelivery.organization_id == org_id))
    ).scalar_one()
    assert delivery.status.value == "suppressed"
    assert delivery.channel.value == "email"


@pytest.mark.asyncio
async def test_email_campaign_persists_resend_id_for_delivery_callbacks(client, db):
    headers, org_id, org_code, plan_id = await _provision_gym(client)
    await _signup_member(client, org_code, plan_id, headers, "tracked@camp.com")
    campaign = await _create_campaign(client, headers, channel="email")

    result = await client.post(f"/api/v1/campaigns/{campaign['id']}/send", headers=headers)

    assert result.status_code == 200, result.text
    delivery = (
        await db.execute(select(CampaignDelivery).where(CampaignDelivery.organization_id == org_id))
    ).scalar_one()
    assert delivery.provider_message_id
    assert delivery.delivery_status == "sent"


@pytest.mark.asyncio
async def test_sms_campaign_requires_consent_phone_and_uses_connected_transport(client, db, monkeypatch):
    from app.integrations.inbox_channels import DeliveryReceipt
    from app.services import campaign_service

    sent_to = []
    callbacks = []

    async def fake_sms(channel, recipient, body, credentials=None, *, status_callback=None):
        sent_to.append((channel.value, recipient, body))
        callbacks.append(status_callback)
        return DeliveryReceipt("SM-test")

    monkeypatch.setattr(campaign_service, "deliver_inbox_message", fake_sms)
    from app.core.config import settings

    monkeypatch.setattr(settings, "inbox_public_webhook_base_url", "https://api.example")
    headers, org_id, org_code, plan_id = await _provision_gym(client)
    opted_in_id = await _signup_member(client, org_code, plan_id, headers, "smsin@camp.com")
    opted_out_id = await _signup_member(client, org_code, plan_id, headers, "smsout@camp.com")
    opted_in = await db.get(OrganizationMember, opted_in_id)
    opted_in.phone = "+15550000001"
    opted_in.marketing_sms_consent = True
    opted_out = await db.get(OrganizationMember, opted_out_id)
    opted_out.phone = "+15550000002"
    await db.commit()

    campaign = await _create_campaign(client, headers, channel="sms")
    preview = await client.get(f"/api/v1/campaigns/preview/{campaign['id']}?limit=8", headers=headers)
    assert preview.status_code == 200, preview.text
    assert preview.json()["count"] == 1
    assert preview.json()["sample"][0]["phone"] == "+15550000001"

    result = await client.post(f"/api/v1/campaigns/{campaign['id']}/send", headers=headers)
    assert result.status_code == 200, result.text
    assert result.json()["sent"] == 1
    assert sent_to == [("sms", "+15550000001", "Come back and save 20% this week.")]
    assert callbacks == [f"https://api.example/api/v1/inbox/webhooks/{org_id}/twilio/status"]
    delivery = (await db.execute(select(CampaignDelivery).where(
        CampaignDelivery.organization_id == org_id,
    ))).scalar_one()
    assert delivery.provider_message_id == "SM-test"
    assert delivery.delivery_status == "queued"


@pytest.mark.asyncio
async def test_campaign_send_limit_is_capped_at_200(client):
    headers, _org_id, _org_code, _plan_id = await _provision_gym(client)
    response = await client.post(
        "/api/v1/campaigns",
        headers=headers,
        json={"title": "Too many", "subject": "Offer", "body": "Hello", "channel": "sms", "send_limit": 201},
    )
    assert response.status_code == 422

    email_campaign = await client.post(
        "/api/v1/campaigns",
        headers=headers,
        json={"title": "Email", "subject": "Offer", "body": "Hello", "channel": "email", "send_limit": 201},
    )
    assert email_campaign.status_code == 201, email_campaign.text


@pytest.mark.asyncio
async def test_campaign_excludes_members_without_channel_consent(client, db):
    headers, org_id, org_code, plan_id = await _provision_gym(client)
    member_id = await _signup_member(
        client, org_code, plan_id, headers, "no-consent@camp.com", marketing_consent=False,
    )
    updated = await client.put(
        f"/api/v1/privacy/members/{member_id}/consent",
        headers={**headers, "Idempotency-Key": "member-email-consent-only"},
        json={"email": True, "sms": False, "in_app": False},
    )
    assert updated.status_code == 200, updated.text

    campaign = await _create_campaign(client, headers, channel="in_app")

    response = await client.post(f"/api/v1/campaigns/{campaign['id']}/send", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["targeted"] == 0
    assert response.json()["sent"] == 0
    assert not (await db.execute(select(CampaignDelivery).where(
        CampaignDelivery.organization_id == org_id,
    ))).scalars().all()

    email_campaign = await _create_campaign(client, headers, channel="email")
    response = await client.post(f"/api/v1/campaigns/{email_campaign['id']}/send", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["targeted"] == 1
    assert response.json()["sent"] == 1


@pytest.mark.asyncio
async def test_lapsed_segment_targets_only_inactive_members(client, db):
    headers, org_id, org_code, plan_id = await _provision_gym(client)
    m1 = await _signup_member(client, org_code, plan_id, headers, "here@camp.com")
    m2 = await _signup_member(client, org_code, plan_id, headers, "gone@camp.com")

    # Two visits ~40 days ago -> lapsed candidates; member m1 also visited yesterday.
    for _id in (m1, m2):
        db.add(
            Attendance(
                organization_id=org_id, member_id=_id, checked_in_at=now_utc() - timedelta(days=40)
            )
        )
    db.add(
        Attendance(
            organization_id=org_id, member_id=m1, checked_in_at=now_utc() - timedelta(days=1)
        )
    )
    await db.commit()

    campaign = await _create_campaign(
        client, headers, channel="in_app", min_days_since_last_visit=30
    )
    r = await client.post(f"/api/v1/campaigns/{campaign['id']}/send", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["targeted"] == 1
    assert r.json()["sent"] == 1

    deliveries = (
        (
            await db.execute(
                select(CampaignDelivery).where(CampaignDelivery.organization_id == org_id)
            )
        )
        .scalars()
        .all()
    )
    assert [d.member_id for d in deliveries] == [m2]


@pytest.mark.asyncio
async def test_scheduled_campaign_fires_when_due(client, db):
    headers, org_id, org_code, plan_id = await _provision_gym(client)
    await _signup_member(client, org_code, plan_id, headers, "scheduled@camp.com")

    campaign = await _create_campaign(client, headers, channel="in_app")
    r = await client.post(
        f"/api/v1/campaigns/{campaign['id']}/schedule",
        headers=headers,
        json={"scheduled_at": (now_utc() - timedelta(minutes=1)).isoformat()},
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "scheduled"

    out = await run_due_campaigns(db, org_id=org_id)
    await db.commit()
    assert out["fired"] == 1
    assert out["sent"] == 1
    assert (await db.get(Campaign, campaign["id"])).status.value == "sent"


@pytest.mark.asyncio
async def test_cancel_draft_and_invalid_transitions(client, db):
    headers, _org_id, org_code, plan_id = await _provision_gym(client)
    campaign = await _create_campaign(client, headers)
    r = await client.post(f"/api/v1/campaigns/{campaign['id']}/cancel", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "cancelled"

    # Sending a cancelled campaign is rejected.
    r = await client.post(f"/api/v1/campaigns/{campaign['id']}/send", headers=headers)
    assert r.status_code == 409
    # Cancelling a sent campaign is rejected.
    c2 = await _create_campaign(client, headers)
    await client.post(f"/api/v1/campaigns/{c2['id']}/send", headers=headers)
    r = await client.post(f"/api/v1/campaigns/{c2['id']}/cancel", headers=headers)
    assert r.status_code == 409


# ------------------------------------------------------------ previews / queries
@pytest.mark.asyncio
async def test_preview_reports_segment_size(client, db):
    headers, _org_id, org_code, plan_id = await _provision_gym(client)
    await _signup_member(client, org_code, plan_id, headers, "p1@camp.com")
    await _signup_member(client, org_code, plan_id, headers, "p2@camp.com")

    campaign = await _create_campaign(client, headers)
    r = await client.get(f"/api/v1/campaigns/preview/{campaign['id']}", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["count"] == 2
    assert len(body["sample"]) == 2
    assert body["sample"][0]["email"].endswith("@camp.com")


@pytest.mark.asyncio
async def test_admin_listing_and_detail(client, db):
    headers, _org_id, org_code, plan_id = await _provision_gym(client)
    await _signup_member(client, org_code, plan_id, headers, "list@camp.com")
    campaign = await _create_campaign(client, headers)
    await client.post(f"/api/v1/campaigns/{campaign['id']}/send", headers=headers)

    r = await client.get("/api/v1/campaigns", headers=headers)
    assert r.status_code == 200, r.text
    listing = r.json()
    assert listing[0]["id"] == campaign["id"]
    assert listing[0]["deliveries"] == 1
    assert listing[0]["sent_count"] == 1

    r = await client.get(f"/api/v1/campaigns/{campaign['id']}", headers=headers)
    assert r.status_code == 200, r.text
    detail = r.json()
    assert detail["title"] == "Summer Blast"
    member = detail["deliveries"][0]
    assert member["member_name"] == "list@camp.com"  # no display name set -> email


@pytest.mark.asyncio
async def test_capability_and_tenant_isolation(client, db):
    headers, _org_id, org_code, plan_id = await _provision_gym(client)
    await _signup_member(client, org_code, plan_id, headers, "iso@camp.com")

    r = await client.post(
        "/api/v1/staff/invites",
        headers=headers,
        json={"role": "front_desk", "email": "desk@camp.com"},
    )
    invite = r.json()["code"]
    r = await client.post(
        "/api/v1/staff/invites/redeem",
        json={"code": invite, "full_name": "Dana", "password": PASSWORD},
    )
    desk = {
        "Authorization": f"Bearer {r.json()['access_token']}",
        "X-Organization-Id": r.json()["organization_id"],
    }

    body = {"title": "Nope", "subject": "no", "body": "not allowed", "channel": "in_app"}
    assert (await client.post("/api/v1/campaigns", headers=desk, json=body)).status_code == 403
    assert (await client.get("/api/v1/campaigns", headers=desk)).status_code == 403

    # Tenant isolation: another gym does not see our campaign.
    _h2, _org2, _c2, _plan2 = await _provision_gym(client, owner_email="other@camp.com")
    campaign = await _create_campaign(client, headers)
    assert (await client.get(f"/api/v1/campaigns/{campaign['id']}", headers=_h2)).status_code == 404
    r = await client.get("/api/v1/campaigns", headers=_h2)
    assert r.status_code == 200, r.text
    assert r.json() == []
