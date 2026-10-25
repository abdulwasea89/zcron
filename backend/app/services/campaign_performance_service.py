"""Explicit staff attribution and estimated campaign cost; no inferred causality."""

from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.constants import CampaignDeliveryStatus, PaymentKind, PaymentStatus
from app.models.campaign import CampaignDelivery, CampaignPaymentAttribution
from app.models.payment import Payment
from app.services.audit_service import record_audit
from app.services.campaign_service import _get_campaign


def performance_totals(campaign, payments: list[Payment], accepted: int) -> dict:
    revenue = {}
    for payment in payments:
        amount = Decimal(str(payment.amount)) - Decimal(str(payment.refunded_amount))
        revenue[payment.currency] = revenue.get(payment.currency, Decimal("0")) + amount
    cost = (campaign.estimated_unit_cost * accepted).quantize(Decimal("0.01")) if campaign.estimated_unit_cost is not None else None
    roi = None
    if cost is not None and cost > 0:
        roi = (revenue.get(campaign.cost_currency, Decimal("0")) - cost) / cost * 100
    return {
        "accepted_recipients": accepted, "attributed_payments": len(payments),
        "attributed_members": len({payment.member_id for payment in payments}),
        "net_revenue_by_currency": {currency: format(amount.quantize(Decimal("0.01")), ".2f") for currency, amount in sorted(revenue.items())},
        "estimated_cost": format(cost.quantize(Decimal("0.01")), ".2f") if cost is not None else None,
        "cost_currency": campaign.cost_currency,
        "estimated_roi_percent": format(roi.quantize(Decimal("0.01")), ".2f") if roi is not None else None,
    }


async def performance(session: AsyncSession, *, org_id: str, campaign_id: str) -> dict:
    campaign = await _get_campaign(session, org_id, campaign_id)
    accepted = (await session.execute(select(CampaignDelivery.id).where(
        CampaignDelivery.organization_id == org_id, CampaignDelivery.campaign_id == campaign.id,
        or_(CampaignDelivery.status == CampaignDeliveryStatus.SENT, CampaignDelivery.provider_message_id.is_not(None)),
    ))).scalars().all()
    payments = list((await session.execute(select(Payment).join(
        CampaignPaymentAttribution, CampaignPaymentAttribution.payment_id == Payment.id,
    ).where(Payment.organization_id == org_id, CampaignPaymentAttribution.organization_id == org_id,
            CampaignPaymentAttribution.campaign_id == campaign.id).order_by(Payment.created_at.desc())
    )).scalars().all())
    return {**performance_totals(campaign, payments, len(accepted)),
            "payments": [{"id": row.id, "member_id": row.member_id, "currency": row.currency,
                          "net_amount": format((Decimal(str(row.amount)) - Decimal(str(row.refunded_amount))).quantize(Decimal("0.01")), ".2f")}
                         for row in payments[:100]],
            "payments_truncated": len(payments) > 100,
            "attribution_basis": "Staff-linked payments after an accepted campaign message; amounts reflect recorded refunds. Costs are estimates, not provider invoices."}


async def attribute_payment(session: AsyncSession, *, org_id: str, campaign_id: str,
                            payment_id: str, actor_id: str) -> None:
    campaign = await _get_campaign(session, org_id, campaign_id)
    payment = await session.get(Payment, payment_id, with_for_update=True)
    if payment is None or payment.organization_id != org_id:
        raise HTTPException(status_code=404, detail="Payment not found.")
    existing = (await session.execute(select(CampaignPaymentAttribution).where(
        CampaignPaymentAttribution.payment_id == payment.id,
    ))).scalar_one_or_none()
    if existing:
        if existing.organization_id != org_id or existing.campaign_id != campaign.id:
            raise HTTPException(status_code=409, detail="This payment is already attributed to another campaign.")
        return
    if (payment.status not in {PaymentStatus.SUCCEEDED, PaymentStatus.PARTIALLY_REFUNDED}
            or payment.kind not in {PaymentKind.MEMBER_FEE, PaymentKind.DAY_PASS} or not payment.member_id):
        raise HTTPException(status_code=422, detail="Choose a successful member payment.")
    delivery = (await session.execute(select(CampaignDelivery).where(
        CampaignDelivery.organization_id == org_id, CampaignDelivery.campaign_id == campaign.id,
        CampaignDelivery.member_id == payment.member_id, CampaignDelivery.status == CampaignDeliveryStatus.SENT,
    ))).scalar_one_or_none()
    if delivery is None or (payment.paid_at or payment.created_at) < (delivery.delivered_at or delivery.created_at):
        raise HTTPException(status_code=422, detail="The payment must follow an accepted message to this campaign recipient.")
    attribution = CampaignPaymentAttribution(organization_id=org_id, campaign_id=campaign.id,
                                             payment_id=payment.id, attributed_by=actor_id)
    session.add(attribution)
    await record_audit(session, action="campaigns.payment_attributed", organization_id=org_id,
                       actor_user_id=actor_id, entity_type="campaign", entity_id=campaign.id,
                       metadata={"payment_id": payment.id})


async def remove_attribution(session: AsyncSession, *, org_id: str, campaign_id: str,
                             payment_id: str, actor_id: str) -> None:
    await _get_campaign(session, org_id, campaign_id)
    row = (await session.execute(select(CampaignPaymentAttribution).where(
        CampaignPaymentAttribution.organization_id == org_id,
        CampaignPaymentAttribution.campaign_id == campaign_id, CampaignPaymentAttribution.payment_id == payment_id,
    ).with_for_update())).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Attributed payment not found.")
    await session.delete(row)
    await record_audit(session, action="campaigns.payment_unattributed", organization_id=org_id,
                       actor_user_id=actor_id, entity_type="campaign", entity_id=campaign_id,
                       metadata={"payment_id": payment_id})
