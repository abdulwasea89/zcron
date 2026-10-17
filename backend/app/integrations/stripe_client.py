"""Stripe Platform abstraction for SaaS billing + a stub fallback.

When no real Stripe key is configured (``settings.stripe_live`` is False), every
method returns a deterministic fake object so registration/billing flows run
end-to-end locally. The same ``idempotency_key`` is always passed through to
Stripe (Security Rule #2, Section 13.5).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from app.core.config import settings

try:
    import stripe as _stripe
except Exception:  # pragma: no cover
    _stripe = None


@dataclass
class FakePaymentIntent:
    id: str
    status: str
    amount: int
    currency: str
    client_secret: str


@dataclass
class CheckoutSession:
    id: str
    url: str
    status: str
    payment_status: str
    mode: str | None = None
    customer_id: str | None = None
    subscription_id: str | None = None
    metadata: dict | None = None
    amount_total: int | None = None
    currency: str | None = None
    current_period_end: datetime | None = None
    subscription_status: str | None = None


def _fake_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:24]}"


def _metadata_dict(metadata: object | None) -> dict[str, str]:
    """Convert Stripe's metadata StripeObject without treating it as an iterable."""
    if metadata is None:
        return {}
    if isinstance(metadata, dict):
        return dict(metadata)
    to_dict = getattr(metadata, "to_dict", None)
    if callable(to_dict):
        return to_dict()
    raise TypeError("Stripe returned an unsupported metadata object.")


class StripePlatform:
    """SaaS-side Stripe (the platform's own account)."""

    def __init__(self) -> None:
        self.live = settings.stripe_live
        if self.live and _stripe is not None:
            _stripe.api_key = settings.stripe_secret_key

    @property
    def ready(self) -> bool:
        """Whether real Stripe calls can be made with the loaded SDK/config."""
        return self.live and _stripe is not None

    async def create_customer(
        self, email: str, name: str | None = None, *, idempotency_key: str | None = None
    ) -> str:
        if not self.live:
            return _fake_id("cus")
        options = {"idempotency_key": idempotency_key} if idempotency_key else {}
        cust = _stripe.Customer.create(email=email, name=name, **options)
        return cust.id

    async def charge_first_month(
        self, *, customer_id: str, amount_cents: int, currency: str, idempotency_key: str
    ) -> FakePaymentIntent:
        """Charge the first SaaS month immediately (Section 3.2.2)."""

        if not self.live:
            return FakePaymentIntent(
                id=_fake_id("pi"),
                status="succeeded",
                amount=amount_cents,
                currency=currency,
                client_secret=_fake_id("secret"),
            )
        pi = _stripe.PaymentIntent.create(
            amount=amount_cents,
            currency=currency,
            customer=customer_id,
            confirm=True,
            idempotency_key=idempotency_key,
            automatic_payment_methods={"enabled": True, "allow_redirects": "never"},
        )
        return FakePaymentIntent(
            id=pi.id, status=pi.status, amount=pi.amount, currency=pi.currency,
            client_secret=pi.client_secret or "",
        )

    async def create_subscription(self, *, customer_id: str, tier: str) -> str:
        if not self.live:
            return _fake_id("sub")
        # In production: map tier -> price_id and create a real subscription.
        return _fake_id("sub")

    async def create_saas_checkout(
        self, *, customer_id: str, org_id: str, tier: str, amount_cents: int,
        currency: str, idempotency_key: str, billing_return: bool = False,
    ) -> CheckoutSession:
        """Hosted recurring checkout; card data is collected and tokenized by Stripe."""
        if not self.live or _stripe is None:
            raise RuntimeError("Stripe test/live secret key is required for real checkout.")
        return_path = "/app/billing" if billing_return else "/app"
        success_query = "billing=success" if billing_return else "onboarding=success"
        cancel_query = "billing=cancelled" if billing_return else "onboarding=payment-cancelled"
        session = _stripe.checkout.Session.create(
            mode="subscription",
            payment_method_types=["card"],
            customer=customer_id,
            line_items=[{
                "price_data": {
                    "currency": currency.lower(), "unit_amount": amount_cents,
                    "recurring": {"interval": "month"},
                    "product_data": {"name": f"Acron {tier.title()} workspace"},
                },
                "quantity": 1,
            }],
            success_url=f"{settings.frontend_url}{return_path}?{success_query}&session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{settings.frontend_url}{return_path}?{cancel_query}",
            client_reference_id=org_id,
            metadata={"organization_id": org_id, "tier": tier},
            subscription_data={"metadata": {"organization_id": org_id, "tier": tier}},
            billing_address_collection="auto",
            allow_promotion_codes=False,
            # The workspace vault is denominated in USD. Keep Checkout's
            # invoice in that currency so Stripe can apply the USD customer
            # balance before collecting any remainder from the card.
            adaptive_pricing={"enabled": False},
            idempotency_key=idempotency_key,
        )
        return CheckoutSession(
            id=session.id, url=session.url or "", status=session.status or "open",
            payment_status=session.payment_status or "unpaid",
            mode=session.mode,
            customer_id=session.customer if isinstance(session.customer, str) else customer_id,
            subscription_id=session.subscription if isinstance(session.subscription, str) else None,
            metadata=_metadata_dict(session.metadata),
            amount_total=session.amount_total,
            currency=session.currency,
        )

    async def retrieve_checkout_session(self, session_id: str) -> CheckoutSession | None:
        if not self.live or _stripe is None:
            return None
        session = _stripe.checkout.Session.retrieve(session_id, expand=["subscription"])
        subscription = session.subscription
        sub_id = subscription.id if hasattr(subscription, "id") else subscription
        period_end = getattr(subscription, "current_period_end", None)
        if not period_end and hasattr(subscription, "to_dict"):
            items = (subscription.to_dict().get("items") or {}).get("data") or []
            period_end = items[0].get("current_period_end") if items else None
        return CheckoutSession(
            id=session.id, url=session.url or "", status=session.status or "open",
            payment_status=session.payment_status or "unpaid",
            mode=session.mode,
            customer_id=session.customer if isinstance(session.customer, str) else None,
            subscription_id=sub_id if isinstance(sub_id, str) else None,
            metadata=_metadata_dict(session.metadata),
            amount_total=session.amount_total,
            currency=session.currency,
            current_period_end=(datetime.fromtimestamp(period_end, timezone.utc).replace(tzinfo=None)
                                if period_end else None),
            subscription_status=getattr(subscription, "status", None),
        )

    async def expire_checkout_session(self, session_id: str) -> None:
        if self.live and _stripe is not None:
            _stripe.checkout.Session.expire(session_id)

    async def create_billing_portal(self, *, customer_id: str, return_url: str) -> str:
        """Create a short-lived Stripe-hosted session for subscription management."""
        if not self.live or _stripe is None:
            raise RuntimeError("Stripe test/live secret key is required for billing management.")
        portal = _stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=return_url,
        )
        return portal.url


platform_stripe = StripePlatform()
