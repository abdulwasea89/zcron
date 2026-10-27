from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.core.constants import CampaignChannel, CampaignDeliveryStatus, Channel
from app.integrations import inbox_channels
from app.integrations.inbox_channels import DeliveryReceipt
from app.models.campaign import Campaign, CampaignDelivery
from app.models.inbox import InboxConversation
from app.models.membership import OrganizationMember
from app.models.user import User
from app.schemas.campaign import CampaignCreateIn
from app.services import campaign_service, inbox_channels_service, inbox_service, members_service


def test_whatsapp_migration_preserves_existing_consent_and_campaigns(monkeypatch):
    from importlib import import_module
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import create_engine

    engine = create_engine("sqlite://")
    migration = import_module("app.db.migrations.versions.d6e7f8a9b0c1_whatsapp_campaigns")
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("CREATE TABLE organization_members (id VARCHAR PRIMARY KEY, marketing_sms_consent BOOLEAN)")
            connection.exec_driver_sql("INSERT INTO organization_members VALUES ('member', 1)")
            connection.exec_driver_sql("CREATE TABLE campaigns (id VARCHAR PRIMARY KEY)")
            connection.exec_driver_sql("INSERT INTO campaigns VALUES ('campaign')")
            monkeypatch.setattr(migration, "op", Operations(MigrationContext.configure(connection)))
            migration.upgrade()
            assert connection.exec_driver_sql("SELECT marketing_sms_consent, marketing_whatsapp_consent FROM organization_members").one() == (1, 0)
            assert connection.exec_driver_sql("SELECT whatsapp_variables FROM campaigns").scalar_one() == "{}"
            migration.downgrade()
            assert connection.exec_driver_sql("SELECT id FROM campaigns").scalar_one() == "campaign"
    finally:
        engine.dispose()


def test_whatsapp_campaign_requires_template_and_valid_variable_values():
    base = {"title": "Offer", "subject": "Offer", "body": "Internal description", "channel": "whatsapp"}
    with pytest.raises(ValidationError):
        CampaignCreateIn(**base)
    with pytest.raises(ValidationError):
        CampaignCreateIn(**base, whatsapp_template_sid="HX" + "a" * 32, whatsapp_variables={"1": "line\nbreak"})
    value = CampaignCreateIn(**base, whatsapp_template_sid="HX" + "a" * 32, whatsapp_variables={"1": "offer"}, member_tag=" Morning ")
    assert value.member_tag == "morning"


@pytest.mark.asyncio
@pytest.mark.parametrize("channel", [CampaignChannel.SMS, CampaignChannel.WHATSAPP])
@pytest.mark.parametrize("sms,whatsapp", [(False, False), (True, False), (False, True), (True, True)])
async def test_phone_campaigns_require_the_correct_channel_consent(monkeypatch, channel, sms, whatsapp):
    member = OrganizationMember(organization_id="org", user_id="user", phone="+14155550123",
                                marketing_sms_consent=sms, marketing_whatsapp_consent=whatsapp)
    campaign = Campaign(organization_id="org", title="Offer", subject="Offer", body="Internal description", channel=channel,
                        whatsapp_template_sid="HX" + "a" * 32 if channel == CampaignChannel.WHATSAPP else None,
                        whatsapp_variables={"1": "offer"})
    delivery = CampaignDelivery(organization_id="org", campaign_id=campaign.id, member_id=member.id)
    calls = []

    async def get(*_args):
        return User(id="user", email="member@example.com", hashed_password="unused", email_verified=True)

    async def credentials(*_args):
        return {"account_sid": "ACtest", "auth_token": "test", "from_number": "+14155550100"}

    async def send(*args, **kwargs):
        calls.append((args, kwargs))
        return DeliveryReceipt("SMprovider")

    monkeypatch.setattr(inbox_channels_service, "get_credentials", credentials)
    monkeypatch.setattr(inbox_channels_service, "webhook_url", lambda *_args: "https://api.example.test/webhook/twilio")
    monkeypatch.setattr(campaign_service, "deliver_inbox_message", send)
    await campaign_service._deliver_member(SimpleNamespace(get=get), org_id="org", campaign=campaign, member=member, delivery=delivery)
    allowed = whatsapp if channel == CampaignChannel.WHATSAPP else sms
    assert bool(calls) is allowed
    assert delivery.status == (CampaignDeliveryStatus.SENT if allowed else CampaignDeliveryStatus.SUPPRESSED)
    if allowed and channel == CampaignChannel.WHATSAPP:
        assert calls[0][0][0] == Channel.WHATSAPP
        assert calls[0][1]["content_sid"] == campaign.whatsapp_template_sid


@pytest.mark.asyncio
async def test_email_campaign_never_claims_a_stub_or_rejected_send_succeeded(monkeypatch):
    from app.integrations.email import EmailSendResult
    member = OrganizationMember(organization_id="org", user_id="user", marketing_email_consent=True)
    campaign = Campaign(organization_id="org", title="Offer", subject="Offer", body="Hello", channel=CampaignChannel.EMAIL)
    delivery = CampaignDelivery(organization_id="org", campaign_id=campaign.id, member_id=member.id)

    async def get(*_args):
        return User(id="user", email="member@example.com", hashed_password="unused", email_verified=True)

    async def send(*_args):
        return EmailSendResult(False)

    monkeypatch.setattr(campaign_service, "send_campaign_email", send)
    await campaign_service._deliver_member(SimpleNamespace(get=get), org_id="org", campaign=campaign, member=member, delivery=delivery)
    assert delivery.status == CampaignDeliveryStatus.FAILED
    assert delivery.delivered_at is None
    assert delivery.error


@pytest.mark.asyncio
@pytest.mark.parametrize("channel", [Channel.SMS, Channel.WHATSAPP])
async def test_stop_revokes_only_the_matching_member_channel(monkeypatch, channel):
    member = OrganizationMember(organization_id="org", user_id="user", marketing_sms_consent=True, marketing_whatsapp_consent=True)
    conv = InboxConversation(organization_id="org", channel=channel, member_id=member.id, contact_handle="+14155550123")

    async def find(*_args, **_kwargs):
        return conv

    async def noop(*_args, **_kwargs):
        pass

    async def result(*_args):
        return {}

    class Session:
        def add(self, _row):
            pass

        async def flush(self):
            pass

        async def get(self, *_args):
            return member

        async def execute(self, *_args):
            return SimpleNamespace(scalars=lambda: [])

    monkeypatch.setattr(inbox_service, "find_or_create", find)
    monkeypatch.setattr(inbox_service, "_thread_out", result)
    monkeypatch.setattr(inbox_service, "record_audit", noop)
    monkeypatch.setattr(inbox_service.events, "inbox_changed", noop)
    monkeypatch.setattr(members_service, "detect_freeze_request_from_message", noop)
    await inbox_service.record_inbound(Session(), org_id="org", channel=channel, handle="+14155550123", body="STOP")
    assert member.marketing_sms_consent is (channel != Channel.SMS)
    assert member.marketing_whatsapp_consent is (channel != Channel.WHATSAPP)


@pytest.mark.asyncio
async def test_whatsapp_transport_uses_content_sid_instead_of_raw_body(monkeypatch):
    sent = []

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            pass

        async def post(self, url, **kwargs):
            sent.append(kwargs["data"])
            return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"sid": "SMprovider"})

    monkeypatch.setattr(inbox_channels.httpx, "AsyncClient", lambda **_kwargs: Client())
    await inbox_channels.deliver(Channel.WHATSAPP, "+14155550123", "This must not be sent as free text", {
        "account_sid": "ACtest", "auth_token": "test", "from_number": "+14155550100",
    }, content_sid="HX" + "a" * 32, content_variables={"1": "offer"})
    assert "Body" not in sent[0]
    assert sent[0]["ContentSid"] == "HX" + "a" * 32
    assert sent[0]["To"] == "whatsapp:+14155550123"
