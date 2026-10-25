from app.api.v1.routes.inbox_webhooks import _apply_campaign_sms_status
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
