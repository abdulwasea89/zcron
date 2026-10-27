import base64
import hashlib
import hmac
import json
from types import SimpleNamespace

import pytest

from app.api.v1.routes import inbox_webhooks
from app.api.v1.routes.inbox_webhooks import _apply_campaign_sms_status, _apply_resend_campaign_status
from app.core.constants import CampaignChannel, CampaignDeliveryStatus
from app.models.campaign import CampaignDelivery


def _delivery():
    return CampaignDelivery(
        organization_id="org", campaign_id="campaign", member_id="member",
        status=CampaignDeliveryStatus.SENT, channel=CampaignChannel.SMS,
        delivery_status="queued",
    )


def test_twilio_campaign_status_advances_to_delivered_and_cannot_downgrade():
    delivery = _delivery()

    _apply_campaign_sms_status(delivery, "sent", None)
    assert delivery.delivery_status == "sent"
    _apply_campaign_sms_status(delivery, "delivered", None)
    assert delivery.delivery_status == "delivered"

    _apply_campaign_sms_status(delivery, "undelivered", "30003")
    assert delivery.delivery_status == "delivered"
    assert delivery.status == CampaignDeliveryStatus.SENT
    assert delivery.error is None


def test_twilio_failed_campaign_status_records_provider_error():
    delivery = _delivery()

    _apply_campaign_sms_status(delivery, "undelivered", "30003")

    assert delivery.delivery_status == "failed"
    assert delivery.status == CampaignDeliveryStatus.FAILED
    assert "30003" in delivery.error


def test_resend_delivery_status_advances_and_preserves_terminal_state():
    delivery = _delivery()

    assert _apply_resend_campaign_status(delivery, "email.delivery_delayed", {})
    assert delivery.delivery_status == "delayed"
    assert not _apply_resend_campaign_status(delivery, "email.delivery_delayed", {})
    assert _apply_resend_campaign_status(delivery, "email.delivered", {})
    assert delivery.delivery_status == "delivered"
    assert not _apply_resend_campaign_status(delivery, "email.bounced", {"bounce": {"message": "late bounce"}})
    assert delivery.status == CampaignDeliveryStatus.SENT
    assert delivery.error is None


def test_resend_complaint_is_retained_after_delivery():
    delivery = _delivery()
    delivery.delivery_status = "delivered"

    assert _apply_resend_campaign_status(delivery, "email.complained", {})
    assert delivery.delivery_status == "complained"
    assert not _apply_resend_campaign_status(delivery, "email.complained", {})


def test_resend_bounce_marks_campaign_delivery_failed():
    delivery = _delivery()

    assert _apply_resend_campaign_status(
        delivery, "email.bounced", {"bounce": {"message": "Mailbox does not exist."}},
    )

    assert delivery.delivery_status == "failed"
    assert delivery.status == CampaignDeliveryStatus.FAILED
    assert delivery.error == "Mailbox does not exist."


def test_resend_webhook_signature_is_verified_and_time_limited(monkeypatch):
    secret_bytes = b"resend-signing-key"
    secret = "whsec_" + base64.b64encode(secret_bytes).decode().rstrip("=")
    msg_id, timestamp, raw = "evt_123", "1793123456", b'{"type":"email.delivered"}'
    signed = msg_id.encode() + b"." + timestamp.encode() + b"." + raw
    signature = base64.b64encode(hmac.new(secret_bytes, signed, hashlib.sha256).digest()).decode()
    monkeypatch.setattr(inbox_webhooks.time, "time", lambda: int(timestamp))

    assert inbox_webhooks._verify_resend_signature(secret, msg_id, timestamp, f"v1,{signature}", raw)
    assert not inbox_webhooks._verify_resend_signature(secret, msg_id, timestamp, f"v1,{signature}", raw + b"x")
    monkeypatch.setattr(inbox_webhooks.time, "time", lambda: int(timestamp) + 301)
    assert not inbox_webhooks._verify_resend_signature(secret, msg_id, timestamp, f"v1,{signature}", raw)


class _WebhookResult:
    def __init__(self, rows):
        self.rows = rows

    def scalars(self):
        return self

    def all(self):
        return self.rows


class _WebhookSession:
    def __init__(self, delivery, member):
        self.delivery = delivery
        self.member = member
        self.added = []

    async def execute(self, _statement):
        return _WebhookResult([self.delivery])

    async def get(self, _model, _key):
        return self.member

    def add(self, value):
        self.added.append(value)


@pytest.mark.asyncio
async def test_resend_complaint_webhook_revokes_email_marketing_consent(monkeypatch):
    secret_bytes = b"resend-signing-key"
    secret = "whsec_" + base64.b64encode(secret_bytes).decode().rstrip("=")
    monkeypatch.setattr(inbox_webhooks.settings, "resend_webhook_secret", secret)
    timestamp = "1793123456"
    monkeypatch.setattr(inbox_webhooks.time, "time", lambda: int(timestamp))
    raw = json.dumps({
        "type": "email.complained",
        "data": {"email_id": "email-123"},
    }).encode()
    msg_id = "evt_complaint"
    signed = msg_id.encode() + b"." + timestamp.encode() + b"." + raw
    signature = base64.b64encode(hmac.new(secret_bytes, signed, hashlib.sha256).digest()).decode()
    request = SimpleNamespace(
        body=lambda: _async_value(raw),
        headers={"svix-id": msg_id, "svix-timestamp": timestamp, "svix-signature": f"v1,{signature}"},
    )
    delivery = _delivery()
    delivery.provider_message_id = "email-123"
    delivery.delivery_status = "delivered"
    member = SimpleNamespace(
        id="member", organization_id="org", marketing_email_consent=True,
        marketing_email_consent_at=None,
    )
    session = _WebhookSession(delivery, member)
    audits = []

    async def record_audit(_session, **kwargs):
        audits.append(kwargs)

    monkeypatch.setattr(inbox_webhooks, "record_audit", record_audit)
    result = await inbox_webhooks.resend_delivery_status(request, session)

    assert result == {"ok": True}
    assert delivery.delivery_status == "complained"
    assert member.marketing_email_consent is False
    assert member.marketing_email_consent_at is not None
    assert len(audits) == 2
    assert audits[-1]["new_values"] == {"email": False}


async def _async_value(value):
    return value
