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
from decimal import Decimal, ROUND_HALF_UP

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.constants import (
    ConnectStatus,
    MemberStatus,
    PaymentStatus,
    Role,
    SaasStatus,
    SubscriptionStatus,
    TIER_PRICE_USD,
)
from app.core.security import now_utc
from app.integrations.email import send_email_safe as send_email
from app.models.organization import Organization
from app.models.membership import OrganizationMember
from app.models.payment import Payment
from app.models.plan import MembershipPlan
from app.models.subscription import Subscription
from app.models.membership_change_request import MembershipChangeRequest
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

    if etype == "checkout.session.completed":
        org_id = (obj.get("metadata") or {}).get("organization_id")
        org = await session.get(Organization, org_id) if org_id else None
        session_id = obj.get("id")
        subscription_id = obj.get("subscription")
        customer_id = obj.get("customer")
        tier = (obj.get("metadata") or {}).get("tier")
        expected = next((amount for plan, amount in TIER_PRICE_USD.items() if plan.value == tier), None)
        if (org is not None and session_id == org.stripe_onboarding_session_id
                and obj.get("mode") == "subscription" and obj.get("payment_status") in {"paid", "no_payment_required"}
                and tier == org.saas_tier.value and expected is not None
                and isinstance(obj.get("amount_total"), int) and 0 <= obj["amount_total"] <= expected * 100 and obj.get("currency") == "usd"
                and customer_id == org.stripe_customer_id
                and subscription_id and customer_id):
            org.stripe_subscription_id = subscription_id
            org.stripe_customer_id = customer_id
            org.saas_status = SaasStatus.ACTIVE
            org.saas_state_changed_at = now_utc()
            org.saas_current_period_end = now_utc() + timedelta(days=30)
            org.onboarding_complete = True
            owner = (await session.execute(select(OrganizationMember).where(
                OrganizationMember.organization_id == org.id,
                OrganizationMember.role == "owner",
            ))).scalar_one_or_none()
            if owner is not None:
                owner.member_status = MemberStatus.ACTIVE
                owner.profile_complete = True
                session.add(owner)
            session.add(org)
            await record_audit(session, action="saas.onboarding_paid", organization_id=org.id,
                               entity_type="organization", entity_id=org.id,
                               metadata={"checkout_session_id": session_id})
            return {"handled": etype}
        return {"ignored": etype, "reason": "unmatched or unpaid checkout"}

    if etype == "customer.subscription.updated":
        org = await _org_by_customer(session, obj.get("customer"))
        if org is not None and obj.get("id") == org.stripe_subscription_id:
            from app.services.workspace_subscription_service import period_end
            from app.core.constants import SaasTier, TIER_MEMBER_CAP
            tier = (obj.get("metadata") or {}).get("tier")
            if obj.get("status") == "active":
                if tier in {"starter", "pro"}:
                    org.saas_tier = SaasTier(tier)
                    org.member_cap = TIER_MEMBER_CAP[org.saas_tier]
                org.saas_status = SaasStatus.ACTIVE
                org.saas_current_period_end = period_end(obj)
                org.saas_grace_until = None
                session.add(org)
            elif obj.get("status") == "canceled":
                org.saas_status = SaasStatus.CANCELLED
                org.saas_state_changed_at = now_utc()
                session.add(org)
        return {"handled": etype}

    if etype == "invoice.payment_succeeded":
        org = await _org_by_customer(session, obj.get("customer"))
        invoice_sub = obj.get("subscription") or ((obj.get("parent") or {}).get("subscription_details") or {}).get("subscription")
        if org is not None and org.saas_status != SaasStatus.CANCELLED and invoice_sub == org.stripe_subscription_id:
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
        if org is not None and obj.get("id") == org.stripe_subscription_id:
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
        return await _connect_payment_failed(session, obj, account_id)

    if etype == "setup_intent.succeeded":
        return await _connect_setup_succeeded(session, obj, account_id)

    if etype == "charge.refunded":
        return await _connect_charge_refunded(session, obj, account_id)

    return {"ignored": etype}


async def _connect_setup_succeeded(session: AsyncSession, obj: dict, account_id: str | None) -> dict:
    metadata = obj.get("metadata") or {}
    org = await _org_by_connect_account(session, account_id)
    member_id = metadata.get("member_id")
    if not org or metadata.get("organization_id") != org.id or not member_id:
        return {"ignored": "setup_intent.succeeded", "reason": "connected account mismatch"}
    member = (await session.execute(select(OrganizationMember).where(
        OrganizationMember.id == member_id,
        OrganizationMember.organization_id == org.id,
        OrganizationMember.role == Role.MEMBER,
    ).with_for_update())).scalar_one_or_none()
    customer = obj.get("customer")
    payment_method = obj.get("payment_method")
    if not member:
        raise HTTPException(status_code=503, detail="Member record is not committed yet; retry webhook.")
    if obj.get("id") == member.stripe_recurring_setup_intent_id:
        return {"handled": "setup_intent.succeeded", "replay": True}
    if customer != member.stripe_customer_id or not isinstance(payment_method, str):
        raise HTTPException(status_code=503, detail="Member payment setup is not committed yet; retry webhook.")
    sub = (await session.execute(select(Subscription).where(
        Subscription.organization_id == org.id,
        Subscription.member_id == member.id,
        Subscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.GRACE]),
    ).order_by(Subscription.started_at.desc()).with_for_update())).scalars().first()
    plan = await session.get(MembershipPlan, sub.plan_id) if sub else None
    if not sub or not plan or plan.billing_type.value != "recurring" or not plan.auto_renew:
        return {"ignored": "setup_intent.succeeded", "reason": "no eligible recurring plan"}
    member.stripe_default_payment_method_id = payment_method
    try:
        from app.integrations.stripe_connect import connect_stripe
        setup_detail = await connect_stripe.inspect_member_setup_intent(
            connected_account_id=account_id, setup_intent_id=obj.get("id"),
        )
        member.stripe_default_payment_method_type = (setup_detail or {}).get("payment_method_type")
    except Exception:
        member.stripe_default_payment_method_type = None
    member.recurring_consent_at = now_utc()
    member.stripe_recurring_setup_intent_id = obj.get("id")
    sub.auto_renew = True
    sub.renewal_attempt_count = 0
    sub.next_renewal_attempt_at = now_utc() if sub.status == SubscriptionStatus.GRACE else None
    session.add(member)
    session.add(sub)
    await record_audit(session, action="member.recurring_billing_enabled",
                       organization_id=org.id, actor_user_id=member.user_id,
                       entity_type="subscription", entity_id=sub.id,
                       metadata={"setup_intent_id": obj.get("id")})
    return {"handled": "setup_intent.succeeded", "member_id": member.id}


async def _payment_by_intent(session: AsyncSession, intent_id: str | None) -> Payment | None:
    if not intent_id:
        return None
    return (
        await session.execute(
            select(Payment).where(Payment.stripe_payment_intent_id == intent_id).with_for_update()
        )
    ).scalar_one_or_none()


async def _connect_payment_succeeded(session: AsyncSession, obj: dict, account_id: str | None) -> dict:
    """Mark the member payment succeeded + activate membership. Idempotent."""

    payment = await _payment_by_intent(session, obj.get("id"))
    if payment is None:
        purpose = (obj.get("metadata") or {}).get("purpose")
        if purpose in {"member_signup", "member_renewal"}:
            raise HTTPException(status_code=503, detail="Member payment record is not committed yet; retry webhook.")
        # Payment intent we don't have a record for (e.g. created off-platform).
        return {"ignored": "payment_intent.succeeded", "reason": "unknown intent"}
    org = await session.get(Organization, payment.organization_id)
    if not org or not account_id or org.stripe_connect_account_id != account_id:
        return {"ignored": "payment_intent.succeeded", "reason": "connected account mismatch"}
    if payment.status in {PaymentStatus.REFUNDED, PaymentStatus.PARTIALLY_REFUNDED}:
        return {"ignored": "payment_intent.succeeded", "reason": "payment already refunded"}
    expected_amount = int((Decimal(str(payment.amount)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    if (obj.get("status") != "succeeded" or type(obj.get("amount_received")) is not int
            or obj["amount_received"] != expected_amount
            or not isinstance(obj.get("currency"), str)
            or obj["currency"].lower() != payment.currency.lower()):
        raise HTTPException(status_code=409, detail="Payment event does not match the recorded amount and currency.")
    replay = payment.status == PaymentStatus.SUCCEEDED
    if not replay:
        payment.status = PaymentStatus.SUCCEEDED
        payment.paid_at = now_utc()
        charge = obj.get("latest_charge")
        if isinstance(charge, str):
            payment.stripe_charge_id = charge
        try:
            from app.integrations.stripe_connect import connect_stripe
            detail = await connect_stripe.inspect_member_intent(
                connected_account_id=account_id, intent_id=obj.get("id"),
            )
            if detail is not None:
                payment.stripe_payment_method_type = detail.payment_method_type
                payment.stripe_payment_method_id = detail.payment_method_id
                payment.stripe_charge_id = detail.charge_id or payment.stripe_charge_id
        except Exception:
            # Settlement is authoritative; optional reporting metadata must not
            # block webhook fulfillment.
            pass
        session.add(payment)

    if (payment.note or "").startswith("member_renewal:"):
        from app.services.recurring_billing_service import complete_recurring_renewal
        await complete_recurring_renewal(session, payment)
        return {"handled": "payment_intent.succeeded", "renewal_payment_id": payment.id}

    change_request = (await session.execute(select(MembershipChangeRequest).where(
        MembershipChangeRequest.payment_id == payment.id,
        MembershipChangeRequest.status == "payment_pending",
    ))).scalar_one_or_none()
    if change_request is not None:
        from app.services.membership_changes_service import _complete_upgrade
        actor = await session.get(OrganizationMember, payment.member_id) if payment.member_id else None
        await _complete_upgrade(session, request=change_request, payment=payment,
                                actor_id=actor.user_id if actor else None)
    elif payment.note == "web_member_signup" and not payment.subscription_id:
        from app.services.memberships_service import finalize_web_signup_payment
        await finalize_web_signup_payment(session, payment)
        return {"handled": "payment_intent.succeeded", "payment_id": payment.id}
    elif replay:
        return {"handled": "payment_intent.succeeded", "replay": True}

    # Activate the subscription/member linked to this payment.
    if payment.subscription_id:
        sub = await session.get(Subscription, payment.subscription_id)
        if sub is not None:
            sub.status = SubscriptionStatus.ACTIVE
            session.add(sub)
    if payment.member_id:
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


async def _connect_payment_failed(session: AsyncSession, obj: dict, account_id: str | None) -> dict:
    payment = await _payment_by_intent(session, obj.get("id"))
    if payment is None:
        purpose = (obj.get("metadata") or {}).get("purpose")
        if purpose in {"member_signup", "member_renewal"}:
            raise HTTPException(status_code=503, detail="Member payment record is not committed yet; retry webhook.")
        return {"ignored": "payment_intent.payment_failed", "reason": "unknown intent"}
    org = await session.get(Organization, payment.organization_id)
    if not org or not account_id or org.stripe_connect_account_id != account_id:
        return {"ignored": "payment_intent.payment_failed", "reason": "connected account mismatch"}
    if payment.status in {PaymentStatus.SUCCEEDED, PaymentStatus.REFUNDED, PaymentStatus.PARTIALLY_REFUNDED}:
        return {"ignored": "payment_intent.payment_failed", "reason": "payment already settled"}
    if payment.status == PaymentStatus.FAILED:
        return {"handled": "payment_intent.payment_failed", "replay": True}
    payment.status = PaymentStatus.FAILED
    error = obj.get("last_payment_error") or {}
    payment.stripe_failure_code = error.get("code")
    payment.stripe_failure_decline_code = error.get("decline_code")
    session.add(payment)
    if (payment.note or "").startswith("member_renewal:"):
        from app.services.recurring_billing_service import fail_recurring_renewal
        await fail_recurring_renewal(session, payment, failure=obj)
        return {"handled": "payment_intent.payment_failed", "renewal_payment_id": payment.id}
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


async def _connect_charge_refunded(session: AsyncSession, obj: dict, account_id: str | None) -> dict:
    """Reflect a refund initiated from the Stripe dashboard on our record."""

    charge_id = obj.get("id")
    payment = (
        await session.execute(select(Payment).where(Payment.stripe_charge_id == charge_id).with_for_update())
    ).scalar_one_or_none()
    if payment is None:
        return {"ignored": "charge.refunded", "reason": "unknown charge"}
    org = await session.get(Organization, payment.organization_id)
    if not org or not account_id or org.stripe_connect_account_id != account_id:
        return {"ignored": "charge.refunded", "reason": "connected account mismatch"}

    amount_refunded = float(obj.get("amount_refunded", 0)) / 100.0
    if amount_refunded > payment.refunded_amount:
        refund_delta = max(0, int(round((amount_refunded - payment.refunded_amount) * 100)))
        from decimal import Decimal
        from app.services.refund_ledger_service import record_refund

        await record_refund(session, payment=payment, amount=Decimal(refund_delta) / 100, source="stripe_webhook")
        payment.refunded_amount = round(amount_refunded, 2)
        payment.refunded_at = now_utc()
        payment.status = (
            PaymentStatus.REFUNDED if payment.refunded_amount + payment.vault_credited_minor / 100 >= payment.amount - 0.01
            else PaymentStatus.PARTIALLY_REFUNDED
        )
        session.add(payment)
        if payment.gym_invoice_id:
            from app.services import gym_invoices_service

            await gym_invoices_service.refresh_after_refund(session, payment=payment, actor_id=None)
        if refund_delta and payment.subscription_id:
            sub = await session.get(Subscription, payment.subscription_id)
            if sub is not None and sub.prepaid_value_minor is not None:
                sub.prepaid_value_minor = max(0, sub.prepaid_value_minor - refund_delta)
                sub.prepaid_value_at = now_utc()
                session.add(sub)
    await record_audit(session, action="payment.webhook_refunded", organization_id=payment.organization_id,
                       entity_type="payment", entity_id=payment.id,
                       new_values={"refunded_amount": payment.refunded_amount})
    return {"handled": "charge.refunded", "payment_id": payment.id}
