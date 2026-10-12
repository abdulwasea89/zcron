"""Stripe webhook event handlers (Section 17 "Stripe Integration Details").

Two endpoints feed this service:

  * Platform (SaaS) — the platform's own account:
      - invoice.payment_succeeded     -> extend the org's SaaS period, mark ACTIVE
      - invoice.payment_failed        -> start the grace workflow (past_due)
      - customer.subscription.deleted -> mark the org cancelled

  * Connect (member payments) — the gym's connected account:
      - account.updated          -> sync stripe_connect_status
      - payment_intent.succeeded -> record the member payment + activate membership
      - payment_intent.payment_failed -> notify the member (retry allowed)
      - charge.refunded          -> reflect the refund on the payment record

Handlers are idempotent: each looks up existing state (by Stripe id) and is safe
to replay, because Stripe delivers webhooks at-least-once. Unknown event types
are acknowledged and ignored so Stripe stops retrying.
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.constants import (
    ConnectStatus,
    MemberStatus,
    PaymentStatus,
    SaasStatus,
    SubscriptionStatus,
)
from app.core.security import now_utc
from app.integrations.email import send_email_safe as send_email
from app.models.organization import Organization
from app.models.payment import Payment
from app.models.subscription import Subscription
from app.models.user import User
from app.services import saas_billing_service
from app.services.audit_service import record_audit


def _obj(event: dict) -> dict:
    """The Stripe event's data.object (the resource the event is about)."""

    return (event.get("data") or {}).get("object") or {}


async def _org_by_customer(session: AsyncSession, customer_id: str | None) -> Organization | None:
    if not customer_id:
        return None
    return (
        await session.execute(
            select(Organization).where(Organization.stripe_customer_id == customer_id)
        )
    ).scalar_one_or_none()


async def _org_by_connect_account(session: AsyncSession, account_id: str | None) -> Organization | None:
    if not account_id:
        return None
    return (
        await session.execute(
            select(Organization).where(Organization.stripe_connect_account_id == account_id)
        )
    ).scalar_one_or_none()


# ----------------------------------------------------------- platform (SaaS)
async def handle_platform_event(session: AsyncSession, event: dict) -> dict:
    etype = event.get("type", "")
    obj = _obj(event)

    if etype == "invoice.payment_succeeded":
        org = await _org_by_customer(session, obj.get("customer"))
        if org is not None:
            org.saas_status = SaasStatus.ACTIVE
            org.saas_grace_until = None
            org.saas_retry_count = 0
            org.saas_state_changed_at = now_utc()
            org.saas_current_period_end = now_utc() + timedelta(days=30)
            session.add(org)
            await record_audit(session, action="saas.payment_succeeded", organization_id=org.id,
                               entity_type="organization", entity_id=org.id)
        return {"handled": etype}

    if etype == "invoice.payment_failed":
        org = await _org_by_customer(session, obj.get("customer"))
        if org is not None:
            await saas_billing_service.handle_failed_charge(session, org=org)
        return {"handled": etype}

    if etype == "customer.subscription.deleted":
        org = await _org_by_customer(session, obj.get("customer"))
        if org is not None:
            org.saas_status = SaasStatus.CANCELLED
            org.saas_retry_count = 0
            org.saas_state_changed_at = now_utc()
            session.add(org)
            await record_audit(session, action="saas.subscription_deleted", organization_id=org.id,
                               entity_type="organization", entity_id=org.id)
        return {"handled": etype}

    return {"ignored": etype}


# ------------------------------------------------------ connect (member pay)
async def handle_connect_event(session: AsyncSession, event: dict) -> dict:
    etype = event.get("type", "")
    obj = _obj(event)
    # On Connect, the event carries the connected account id at the top level.
    account_id = event.get("account")

    if etype == "account.updated":
        org = await _org_by_connect_account(session, account_id)
        if org is not None:
            charges_enabled = bool(obj.get("charges_enabled"))
            org.stripe_connect_status = (
                ConnectStatus.ACTIVE if charges_enabled else ConnectStatus.RESTRICTED
            )
            org.checklist_stripe_connected = charges_enabled or org.checklist_stripe_connected
            session.add(org)
            await record_audit(session, action="connect.account_updated", organization_id=org.id,
                               entity_type="organization", entity_id=org.id,
                               new_values={"status": org.stripe_connect_status.value})
        return {"handled": etype}

    if etype == "payment_intent.succeeded":
        return await _connect_payment_succeeded(session, obj, account_id)

    if etype == "payment_intent.payment_failed":
        return await _connect_payment_failed(session, obj)

    if etype == "charge.refunded":
        return await _connect_charge_refunded(session, obj)

    return {"ignored": etype}


async def _payment_by_intent(session: AsyncSession, intent_id: str | None) -> Payment | None:
    if not intent_id:
        return None
    return (
        await session.execute(
            select(Payment).where(Payment.stripe_payment_intent_id == intent_id)
        )
    ).scalar_one_or_none()


async def _connect_payment_succeeded(session: AsyncSession, obj: dict, account_id: str | None) -> dict:
    """Mark the member payment succeeded + activate membership. Idempotent."""

    payment = await _payment_by_intent(session, obj.get("id"))
    if payment is None:
        # Payment intent we don't have a record for (e.g. created off-platform).
        return {"ignored": "payment_intent.succeeded", "reason": "unknown intent"}
    if payment.status == PaymentStatus.SUCCEEDED:
        return {"handled": "payment_intent.succeeded", "replay": True}

    payment.status = PaymentStatus.SUCCEEDED
    payment.paid_at = now_utc()
    charge = obj.get("latest_charge")
    if isinstance(charge, str):
        payment.stripe_charge_id = charge
    session.add(payment)

    # Activate the subscription/member linked to this payment.
    if payment.subscription_id:
        sub = await session.get(Subscription, payment.subscription_id)
        if sub is not None:
            sub.status = SubscriptionStatus.ACTIVE
            session.add(sub)
    if payment.member_id:
        from app.models.membership import OrganizationMember

        member = await session.get(OrganizationMember, payment.member_id)
        if member is not None:
            member.member_status = MemberStatus.ACTIVE
            if member.joined_at is None:
                member.joined_at = now_utc()
            session.add(member)
            from app.services.family_service import sync_family_status

            await sync_family_status(session, payment.organization_id, member.id, MemberStatus.ACTIVE)
            from app.services.referrals_service import qualify_referral_for_member

            await qualify_referral_for_member(
                session, org_id=payment.organization_id, member_id=member.id
            )

    await record_audit(session, action="payment.webhook_succeeded", organization_id=payment.organization_id,
                       entity_type="payment", entity_id=payment.id)
    return {"handled": "payment_intent.succeeded", "payment_id": payment.id}


async def _connect_payment_failed(session: AsyncSession, obj: dict) -> dict:
    payment = await _payment_by_intent(session, obj.get("id"))
    if payment is None:
        return {"ignored": "payment_intent.payment_failed", "reason": "unknown intent"}
    payment.status = PaymentStatus.FAILED
    session.add(payment)
    if payment.member_id:
        from app.models.membership import OrganizationMember

        member = await session.get(OrganizationMember, payment.member_id)
        user = await session.get(User, member.user_id) if member else None
        if user is not None:
            await send_email(user.email, "Payment failed",
                             "Your membership payment failed. Please retry to keep your access.")
    await record_audit(session, action="payment.webhook_failed", organization_id=payment.organization_id,
                       entity_type="payment", entity_id=payment.id)
    return {"handled": "payment_intent.payment_failed", "payment_id": payment.id}


async def _connect_charge_refunded(session: AsyncSession, obj: dict) -> dict:
    """Reflect a refund initiated from the Stripe dashboard on our record."""

    charge_id = obj.get("id")
    payment = (
        await session.execute(select(Payment).where(Payment.stripe_charge_id == charge_id))
    ).scalar_one_or_none()
    if payment is None:
        return {"ignored": "charge.refunded", "reason": "unknown charge"}

    amount_refunded = float(obj.get("amount_refunded", 0)) / 100.0
    if amount_refunded > 0:
        payment.refunded_amount = round(amount_refunded, 2)
        payment.refunded_at = now_utc()
        payment.status = (
            PaymentStatus.REFUNDED if payment.refunded_amount >= payment.amount - 0.01
            else PaymentStatus.PARTIALLY_REFUNDED
        )
        session.add(payment)
    await record_audit(session, action="payment.webhook_refunded", organization_id=payment.organization_id,
                       entity_type="payment", entity_id=payment.id,
                       new_values={"refunded_amount": payment.refunded_amount})
    return {"handled": "charge.refunded", "payment_id": payment.id}
