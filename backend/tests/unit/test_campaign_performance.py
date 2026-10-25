from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.core.constants import CampaignDeliveryStatus, PaymentKind, PaymentStatus
from app.models.campaign import Campaign, CampaignDelivery, CampaignPaymentAttribution
from app.models.payment import Payment
from app.services import campaign_performance_service as metrics


def test_campaign_roi_uses_only_cost_currency_and_deducts_refunds():
    campaign = Campaign(organization_id="org", title="Offer", subject="Offer", body="Offer",
                        estimated_unit_cost=Decimal("0.05"), cost_currency="USD")
    payments = [Payment(organization_id="org", member_id="member", amount=100, refunded_amount=20, currency="USD"),
                Payment(organization_id="org", member_id="member", amount=9000, currency="EUR")]
    result = metrics.performance_totals(campaign, payments, 100)
    assert result["estimated_cost"] == "5.00"
    assert result["estimated_roi_percent"] == "1500.00"
    assert result["net_revenue_by_currency"] == {"EUR": "9000.00", "USD": "80.00"}
    assert result["attributed_members"] == 1
    campaign.estimated_unit_cost = None
    assert metrics.performance_totals(campaign, payments, 100)["estimated_roi_percent"] is None
    campaign.estimated_unit_cost = Decimal("0.000001")
    assert metrics.performance_totals(campaign, payments, 1)["estimated_roi_percent"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [None, "foreign", "before_message", "not_recipient", "failed_payment", "other_campaign", "non_sale"])
async def test_payment_attribution_is_scoped_validated_and_idempotent(monkeypatch, failure):
    sent = datetime(2026, 1, 1)
    campaign = Campaign(id="campaign", organization_id="org", title="Offer", subject="Offer", body="Offer")
    payment = Payment(id="payment", organization_id="other" if failure == "foreign" else "org", member_id="member",
                      amount=100, status=PaymentStatus.FAILED if failure == "failed_payment" else PaymentStatus.SUCCEEDED,
                      kind=PaymentKind.TRAINER_PAYOUT if failure == "non_sale" else PaymentKind.MEMBER_FEE,
                      paid_at=sent - timedelta(days=1) if failure == "before_message" else sent + timedelta(days=1))
    delivery = CampaignDelivery(organization_id="org", campaign_id=campaign.id, member_id="member",
                                status=CampaignDeliveryStatus.SENT, delivered_at=sent)
    saved = []
    audits = []

    class Session:
        async def get(self, model, _id, **kwargs):
            if model is Campaign:
                return campaign
            assert kwargs["with_for_update"] is True
            return payment

        async def execute(self, query):
            if "campaign_payment_attributions" in str(query):
                value = (SimpleNamespace(organization_id="org", campaign_id="another")
                         if failure == "other_campaign" else saved[0] if saved else None)
            else:
                assert "campaign_deliveries.organization_id" in str(query)
                value = None if failure == "not_recipient" else delivery
            return SimpleNamespace(scalar_one_or_none=lambda: value)

        def add(self, row):
            saved.append(row)

    async def audit(*_args, **kwargs):
        audits.append(kwargs)

    monkeypatch.setattr(metrics, "record_audit", audit)
    session = Session()
    if failure:
        with pytest.raises(HTTPException):
            await metrics.attribute_payment(session, org_id="org", campaign_id=campaign.id, payment_id=payment.id, actor_id="owner")
        assert saved == []
    else:
        await metrics.attribute_payment(session, org_id="org", campaign_id=campaign.id, payment_id=payment.id, actor_id="owner")
        await metrics.attribute_payment(session, org_id="org", campaign_id=campaign.id, payment_id=payment.id, actor_id="owner")
        assert len(saved) == 1 and isinstance(saved[0], CampaignPaymentAttribution)
        assert audits[0]["metadata"] == {"payment_id": payment.id}


def test_attribution_migration_preserves_campaigns_and_prevents_double_attribution(monkeypatch):
    from importlib import import_module
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import create_engine
    from sqlalchemy.exc import IntegrityError

    engine = create_engine("sqlite://")
    migration = import_module("app.db.migrations.versions.e7f8a9b0c1d2_campaign_attribution")
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("CREATE TABLE campaigns (id VARCHAR PRIMARY KEY)")
            connection.exec_driver_sql("INSERT INTO campaigns VALUES ('existing')")
            monkeypatch.setattr(migration, "op", Operations(MigrationContext.configure(connection)))
            migration.upgrade()
            assert connection.exec_driver_sql("SELECT cost_currency FROM campaigns").scalar_one() == "USD"
            connection.exec_driver_sql("INSERT INTO campaign_payment_attributions (id, created_at, updated_at, organization_id, campaign_id, payment_id, attributed_by) VALUES ('one', '2026-01-01', '2026-01-01', 'org', 'existing', 'payment', 'owner')")
            with pytest.raises(IntegrityError):
                connection.exec_driver_sql("INSERT INTO campaign_payment_attributions (id, created_at, updated_at, organization_id, campaign_id, payment_id, attributed_by) VALUES ('two', '2026-01-01', '2026-01-01', 'org', 'different', 'payment', 'owner')")
            migration.downgrade()
            assert connection.exec_driver_sql("SELECT id FROM campaigns").scalar_one() == "existing"
    finally:
        engine.dispose()
