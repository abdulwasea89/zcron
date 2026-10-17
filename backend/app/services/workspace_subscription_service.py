"""Stripe-backed workspace changes and invoice-credit vault.

Stripe is the balance ledger: never synthesize money from plan sticker prices.
All amounts are integer minor units, and only the tenant's saved customer and
subscription identifiers are used.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlmodel import select

from app.core.constants import SaasStatus, SaasTier, TIER_MEMBER_CAP, TIER_PRICE_USD
from app.core.security import now_utc
from app.integrations.stripe_client import platform_stripe
from app.models.organization import Organization
from app.services.audit_service import record_audit
from app.services.saas_billing_service import _member_count


def plain(value):
    return value.to_dict() if hasattr(value, "to_dict") else value


async def stripe_call(method, *args, **kwargs):
    if not platform_stripe.ready:
        raise HTTPException(503, "Stripe billing is not configured.")
    import stripe
    try:
        return plain(await asyncio.to_thread(method, *args, **kwargs))
    except stripe.CardError as exc:
        raise HTTPException(402, "Payment needs attention. Update your payment method in the billing portal, then retry.") from exc
    except stripe.StripeError as exc:
        raise HTTPException(503, "Stripe could not complete this billing action. Your request can be retried safely.") from exc


def period_end(sub):
    items = (sub.get("items") or {}).get("data") or []
    value = sub.get("current_period_end") or (items[0].get("current_period_end") if items else None)
    return datetime.fromtimestamp(value, timezone.utc).replace(tzinfo=None) if value else None


async def subscription(org):
    import stripe
    if not org.stripe_subscription_id:
        raise HTTPException(409, "No workspace subscription is linked. Resume a plan from Billing.")
    sub = await stripe_call(stripe.Subscription.retrieve, org.stripe_subscription_id)
    if sub.get("customer") != org.stripe_customer_id:
        raise HTTPException(409, "Subscription does not match this workspace.")
    return sub


async def vault(org):
    import stripe
    if not org.stripe_customer_id:
        return {"currency": "usd", "available_credit": 0, "transactions": [], "has_more": False}
    customer = await stripe_call(stripe.Customer.retrieve, org.stripe_customer_id)
    transactions = await stripe_call(stripe.Customer.list_balance_transactions, org.stripe_customer_id, limit=50)
    balances = customer.get("invoice_credit_balance") or {}
    balance = balances.get("usd", customer.get("balance", 0))
    return {
        "currency": "usd", "available_credit": max(0, -balance),
        "has_more": transactions.get("has_more", False),
        "transactions": [{"id": row["id"], "amount": -row["amount"],
                          "currency": row["currency"], "created": row["created"],
                          "description": row.get("description") or row["type"].replace("_", " "),
                          "type": row["type"]} for row in transactions.get("data", [])],
    }


async def lock_org(session, org):
    await session.execute(select(Organization).where(Organization.id == org.id).with_for_update())
    await session.refresh(org)


async def change_plan(session, *, org, tier, actor_id, key, direction):
    import stripe
    await lock_org(session, org)
    if tier not in (SaasTier.STARTER, SaasTier.PRO):
        raise HTTPException(422, "Contact support for Enterprise billing.")
    if org.saas_status != SaasStatus.ACTIVE:
        raise HTTPException(409, "Resume or settle your current subscription before changing plans.")
    if direction == "upgrade" and TIER_PRICE_USD[tier] <= TIER_PRICE_USD[org.saas_tier]:
        raise HTTPException(409, "Choose a higher priced plan.")
    if direction == "downgrade" and TIER_PRICE_USD[tier] >= TIER_PRICE_USD[org.saas_tier]:
        raise HTTPException(409, "Choose a lower priced plan.")
    count = await _member_count(session, org.id)
    if count > TIER_MEMBER_CAP[tier]:
        raise HTTPException(409, f"This plan supports {TIER_MEMBER_CAP[tier]} members; your workspace has {count}.")
    sub = await subscription(org)
    items = (sub.get("items") or {}).get("data", [])
    if sub.get("status") != "active" or len(items) != 1 or sub.get("schedule"):
        raise HTTPException(409, "Resolve the current subscription or its scheduled change in Stripe first.")
    if sub.get("cancel_at_period_end"):
        raise HTTPException(409, "Resume the scheduled cancellation before changing tiers.")
    price = items[0]["price"]
    if price.get("currency") != "usd" or (price.get("recurring") or {}).get("interval") != "month":
        raise HTTPException(409, "This subscription requires a custom billing change.")
    if direction == "downgrade":
        # Schedule the lower tier for the next period. Replacing the item now
        # would silently remove service during time the customer has paid for.
        schedule = await stripe_call(stripe.SubscriptionSchedule.create, from_subscription=sub["id"],
                                     idempotency_key=f"{key}:schedule")
        phases = schedule.get("phases") or []
        current_phase = phases[-1] if phases else {}
        end = (items[0].get("current_period_end") or sub.get("current_period_end"))
        start = current_phase.get("start_date") or items[0].get("current_period_start") or sub.get("current_period_start")
        if not start or not end or end <= int(now_utc().replace(tzinfo=timezone.utc).timestamp()):
            await stripe_call(stripe.SubscriptionSchedule.release, schedule["id"])
            raise HTTPException(409, "Stripe did not return a valid billing period for this change.")
        product_id = price["product"] if isinstance(price["product"], str) else price["product"]["id"]
        next_price = await stripe_call(stripe.Price.create, currency="usd",
            unit_amount=int(TIER_PRICE_USD[tier] * 100), product=product_id,
            recurring={"interval": "month"}, metadata={"organization_id": org.id, "tier": tier.value},
            idempotency_key=f"{key}:price")
        current_items = current_phase.get("items") or [{"price": price["id"], "quantity": items[0].get("quantity") or 1}]
        current_items = [{
            "price": item["price"] if isinstance(item.get("price"), str) else item["price"]["id"],
            "quantity": item.get("quantity") or 1,
        } for item in current_items]
        try:
            await stripe_call(stripe.SubscriptionSchedule.modify, schedule["id"],
                end_behavior="release", proration_behavior="none",
                phases=[
                    {"start_date": start, "end_date": end,
                     "items": current_items,
                     "proration_behavior": "none"},
                    {"start_date": end, "duration": {"interval": "month", "interval_count": 1},
                     "items": [{"price": next_price["id"], "quantity": 1}],
                     "metadata": {"organization_id": org.id, "tier": tier.value},
                     "proration_behavior": "none"},
                ], idempotency_key=f"{key}:phase")
        except Exception:
            # Avoid leaving a newly-created schedule attached if its phase edit
            # failed; the original subscription remains in effect.
            await stripe_call(stripe.SubscriptionSchedule.release, schedule["id"])
            raise
        await record_audit(session, action="saas.downgrade_scheduled", organization_id=org.id,
                           actor_user_id=actor_id, entity_type="organization", entity_id=org.id,
                           new_values={"tier": tier.value, "effective_at": end})
        return {"message": "Downgrade scheduled for the end of your paid period. Your current tier stays active until then."}
    # error_if_incomplete keeps the existing plan if additional payment fails.
    # Stripe calculates prorations and consumes invoice credit before card money.
    updated = await stripe_call(
        stripe.Subscription.modify, sub["id"],
        items=[{"id": items[0]["id"], "price_data": {
            "currency": "usd", "unit_amount": int(TIER_PRICE_USD[tier] * 100),
            "recurring": {"interval": "month"}, "product": price["product"],
        }}], payment_behavior="error_if_incomplete", proration_behavior="always_invoice",
        cancel_at_period_end=False, metadata={"organization_id": org.id, "tier": tier.value},
        idempotency_key=key,
    )
    if updated.get("status") != "active":
        raise HTTPException(409, "Stripe has not activated the changed plan.")
    org.saas_tier = tier
    org.member_cap = TIER_MEMBER_CAP[tier]
    org.saas_current_period_end = period_end(updated)
    session.add(org)
    await record_audit(session, action=f"saas.{direction}", organization_id=org.id,
                       actor_user_id=actor_id, entity_type="organization", entity_id=org.id,
                       new_values={"tier": tier.value})
    return {"message": "Plan updated. Stripe applied the prorated charge or invoice credit."}


async def cancel(session, *, org, actor_id, key, timing):
    import stripe
    await lock_org(session, org)
    sub = await subscription(org)
    if sub.get("status") == "canceled":
        org.saas_status = SaasStatus.CANCELLED
    elif timing == "period_end":
        await stripe_call(stripe.Subscription.modify, sub["id"], cancel_at_period_end=True, idempotency_key=key)
    else:
        # Stripe generates the final prorated invoice; negative amounts become
        # invoice credit. Do not also add a manual balance transaction (double credit).
        await stripe_call(stripe.Subscription.cancel, sub["id"], prorate=True, invoice_now=True,
                          idempotency_key=key)
        org.saas_status = SaasStatus.CANCELLED
        org.saas_state_changed_at = now_utc()
    # Cancellation must never reset completed onboarding or revoke login.
    session.add(org)
    await record_audit(session, action="saas.cancellation", organization_id=org.id,
                       actor_user_id=actor_id, entity_type="organization", entity_id=org.id,
                       new_values={"timing": timing})
    return {"message": "Cancellation scheduled for the end of your paid period." if timing == "period_end"
            else "Subscription cancelled. Any unused credit is kept in your vault for future invoices."}


async def resume(session, *, org, actor_id, key):
    import stripe
    await lock_org(session, org)
    sub = await subscription(org)
    if sub.get("status") == "active":
        await stripe_call(stripe.Subscription.modify, sub["id"], cancel_at_period_end=False, idempotency_key=key)
        org.saas_status = SaasStatus.ACTIVE
        session.add(org)
        return {"message": "Your subscription will continue.", "checkout_url": None}
    if sub.get("status") != "canceled":
        raise HTTPException(409, "Settle your existing subscription through the billing portal first.")
    if org.stripe_onboarding_session_id:
        prior = await platform_stripe.retrieve_checkout_session(org.stripe_onboarding_session_id)
        if prior and prior.status == "open" and prior.customer_id == org.stripe_customer_id:
            # Do not reuse an open session: its invoice may have been created
            # before a cancellation credit landed on the customer. A fresh
            # Checkout session creates a fresh invoice that applies the latest
            # customer balance.
            await platform_stripe.expire_checkout_session(prior.id)
    checkout = await platform_stripe.create_saas_checkout(
        customer_id=org.stripe_customer_id, org_id=org.id, tier=org.saas_tier.value,
        amount_cents=int(TIER_PRICE_USD[org.saas_tier] * 100), currency="usd",
        idempotency_key=key, billing_return=True,
    )
    org.stripe_onboarding_session_id = checkout.id
    session.add(org)
    await record_audit(session, action="saas.resume_requested", organization_id=org.id,
                       actor_user_id=actor_id, entity_type="organization", entity_id=org.id)
    return {"message": "Your available credit will be applied by Stripe.", "checkout_url": checkout.url}


async def cancel_scheduled_change(session, *, org, actor_id, key):
    import stripe
    await lock_org(session, org)
    sub = await subscription(org)
    schedule_id = sub.get("schedule")
    if not schedule_id:
        raise HTTPException(409, "There is no scheduled tier downgrade to cancel.")
    await stripe_call(stripe.SubscriptionSchedule.release, schedule_id, idempotency_key=key)
    await record_audit(session, action="saas.scheduled_downgrade_cancelled", organization_id=org.id,
                       actor_user_id=actor_id, entity_type="organization", entity_id=org.id)
    return {"message": "The scheduled downgrade was cancelled. Your current tier will continue."}
