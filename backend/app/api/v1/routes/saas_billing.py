"""SaaS subscription billing API routes (Section 3). Owner-only, web-only."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Header
from fastapi.responses import JSONResponse
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_org, get_session, require_capability
from app.core.permissions import Capability
from app.core.constants import Role
from app.api.deps import require_role
from app.services import workspace_subscription_service as workspace
from app.services import idempotency_service as idempotency
from app.schemas.saas_billing import CancelSubscriptionRequest, SubscriptionCheckoutConfirm
from app.core.constants import SaasTier, SaasStatus, TIER_MEMBER_CAP, TIER_PRICE_USD
from app.core.security import now_utc
from app.core.tenancy import TenantContext
from app.models.organization import Organization
from app.schemas.saas_billing import BillingPortalOut, InvoiceOut, SaasStatusOut, TierChangeRequest
from app.core.config import settings
from app.integrations.stripe_client import platform_stripe
from app.services import saas_billing_service as billing

router = APIRouter()


async def mutate(session, ctx, key, operation, body, callback):
    claim = await idempotency.claim(session, key=key, endpoint=f"saas/{operation}/{ctx.org_id}",
                                    body=body, organization_id=ctx.org_id, user_id=ctx.user_id)
    if not claim.claimed:
        return JSONResponse(json.loads(claim.cached_response), status_code=claim.cached_code)
    result = await callback()
    await idempotency.complete(session, claim.record, code=200, body=json.dumps(result))
    return result



@router.post("/portal", response_model=BillingPortalOut)
async def billing_portal(
    ctx: TenantContext = Depends(require_capability(Capability.MANAGE_SETTINGS)),
    org: Organization = Depends(get_org),
):
    """Open Stripe's hosted billing page for the current workspace customer."""
    if not org.stripe_customer_id:
        raise HTTPException(status_code=409, detail="No Stripe customer is linked to this workspace.")
    try:
        url = await platform_stripe.create_billing_portal(
            customer_id=org.stripe_customer_id,
            return_url=f"{settings.frontend_url.rstrip('/')}/app/billing",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Stripe billing management is unavailable. Check the Stripe Customer Portal settings and try again.",
        ) from exc
    return BillingPortalOut(url=url)


@router.get("/status", response_model=SaasStatusOut)
async def saas_status(
    ctx: TenantContext = Depends(require_capability(Capability.MANAGE_SETTINGS)),
    org: Organization = Depends(get_org),
    session: AsyncSession = Depends(get_session),
):
    data = await billing.status(session, org=org)
    return SaasStatusOut(**data)


@router.post("/upgrade")
async def upgrade(data: TierChangeRequest, key: str = Header(alias="Idempotency-Key"),
                  ctx=Depends(require_role(Role.OWNER)), org=Depends(get_org), session=Depends(get_session)):
    return await mutate(session, ctx, key, "upgrade", data.model_dump(mode="json"),
                        lambda: workspace.change_plan(session, org=org, tier=data.tier, actor_id=ctx.user_id,
                                                      key=f"{org.id}:{key}", direction="upgrade"))


@router.post("/downgrade")
async def downgrade(data: TierChangeRequest, key: str = Header(alias="Idempotency-Key"),
                    ctx=Depends(require_role(Role.OWNER)), org=Depends(get_org), session=Depends(get_session)):
    return await mutate(session, ctx, key, "downgrade", data.model_dump(mode="json"),
                        lambda: workspace.change_plan(session, org=org, tier=data.tier, actor_id=ctx.user_id,
                                                      key=f"{org.id}:{key}", direction="downgrade"))


@router.post("/cancel")
async def cancel(data: CancelSubscriptionRequest, key: str = Header(alias="Idempotency-Key"),
                 ctx=Depends(require_role(Role.OWNER)), org=Depends(get_org), session=Depends(get_session)):
    return await mutate(session, ctx, key, "cancel", data.model_dump(mode="json"),
                        lambda: workspace.cancel(session, org=org, actor_id=ctx.user_id,
                                                 key=f"{org.id}:{key}", timing=data.timing))


@router.post("/resume")
async def resume(key: str = Header(alias="Idempotency-Key"), ctx=Depends(require_role(Role.OWNER)),
                 org=Depends(get_org), session=Depends(get_session)):
    return await mutate(session, ctx, key, "resume", {},
                        lambda: workspace.resume(session, org=org, actor_id=ctx.user_id, key=f"{org.id}:{key}"))


@router.post("/schedule/cancel")
async def cancel_scheduled_change(key: str = Header(alias="Idempotency-Key"),
                 ctx=Depends(require_role(Role.OWNER)), org=Depends(get_org), session=Depends(get_session)):
    return await mutate(session, ctx, key, "cancel-scheduled-change", {},
                        lambda: workspace.cancel_scheduled_change(session, org=org, actor_id=ctx.user_id,
                                                                  key=f"{org.id}:{key}"))


@router.get("/vault")
async def vault(ctx=Depends(require_role(Role.OWNER)), org=Depends(get_org)):
    return await workspace.vault(org)


@router.get("/subscription")
async def subscription(ctx=Depends(require_role(Role.OWNER)), org=Depends(get_org)):
    sub = await workspace.subscription(org)
    pending_tier = None
    if sub.get("schedule"):
        import stripe
        schedule = await workspace.stripe_call(stripe.SubscriptionSchedule.retrieve, sub["schedule"])
        phases = schedule.get("phases") or []
        if len(phases) > 1:
            pending_tier = ((phases[-1].get("metadata") or {}).get("tier"))
    return {"cancel_at_period_end": sub.get("cancel_at_period_end", False),
            "stripe_status": sub.get("status"), "period_end": workspace.period_end(sub),
            "scheduled_tier": pending_tier}


@router.post("/confirm")
async def confirm_checkout(data: SubscriptionCheckoutConfirm,
    ctx=Depends(require_role(Role.OWNER)), org=Depends(get_org), session=Depends(get_session)):
    if data.session_id != org.stripe_onboarding_session_id:
        raise HTTPException(400, "Checkout session does not match this workspace.")
    checkout = await platform_stripe.retrieve_checkout_session(data.session_id)
    if not checkout or checkout.status != "complete" or checkout.mode != "subscription":
        raise HTTPException(402, "Stripe has not completed this subscription checkout.")
    metadata = checkout.metadata or {}
    tier_value = metadata.get("tier")
    try:
        tier = SaasTier(tier_value)
    except (ValueError, TypeError):
        raise HTTPException(402, "Checkout plan could not be verified.")
    expected = TIER_PRICE_USD.get(tier)
    if (expected is None or metadata.get("organization_id") != org.id
            or checkout.payment_status not in {"paid", "no_payment_required"}
            or checkout.customer_id != org.stripe_customer_id
            or not checkout.subscription_id or checkout.amount_total is None
            or not 0 <= checkout.amount_total <= int(expected * 100)):
        raise HTTPException(402, "Stripe has not confirmed the subscription payment.")
    import stripe
    subscription_data = await workspace.stripe_call(stripe.Subscription.retrieve, checkout.subscription_id)
    if subscription_data.get("customer") != org.stripe_customer_id or subscription_data.get("status") != "active":
        raise HTTPException(402, "Stripe has not activated this subscription.")
    org.stripe_subscription_id = checkout.subscription_id
    org.saas_tier = tier
    org.member_cap = TIER_MEMBER_CAP[tier]
    org.saas_status = SaasStatus.ACTIVE
    org.saas_current_period_end = workspace.period_end(subscription_data)
    org.saas_grace_until = None
    org.saas_retry_count = 0
    org.saas_state_changed_at = now_utc()
    session.add(org)
    await session.flush()
    return await billing.status(session, org=org)


@router.get("/invoices", response_model=list[InvoiceOut])
async def invoices(
    ctx: TenantContext = Depends(require_capability(Capability.MANAGE_SETTINGS)),
    session: AsyncSession = Depends(get_session),
):
    return [
        InvoiceOut(id=p.id, amount=p.amount, currency=p.currency, status=p.status.value,
                   created_at=p.created_at)
        for p in await billing.list_invoices(session, org_id=ctx.org_id)
    ]


@router.get("/invoices/{invoice_id}/pdf")
async def invoice_pdf(
    invoice_id: str,
    ctx: TenantContext = Depends(require_capability(Capability.MANAGE_SETTINGS)),
    org: Organization = Depends(get_org),
    session: AsyncSession = Depends(get_session),
):
    pdf_bytes = await billing.get_invoice_pdf(session, invoice_id=invoice_id, org=org)
    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="invoice-{invoice_id[:12]}.pdf"',
        },
    )
