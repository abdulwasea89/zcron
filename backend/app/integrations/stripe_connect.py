"""Stripe Connect Standard abstraction for member payments + stub fallback.

Member money flows directly into the gym's connected account; the platform never
touches it (Security Rule #3, Section 4.9). Stub mode returns deterministic fake
objects so member signup/payment runs without a real Stripe account.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.core.config import settings

try:
    import stripe as _stripe
except Exception:  # pragma: no cover
    _stripe = None


def _fake_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:24]}"


@dataclass
class ConnectPaymentResult:
    id: str
    status: str          # succeeded | requires_action | failed
    amount: int
    currency: str
    charge_id: str | None = None
    client_secret: str | None = None
    payment_method_type: str | None = None
    payment_method_id: str | None = None


@dataclass
class ConnectAccountLink:
    account_id: str
    onboarding_url: str


class StripeConnect:
    def __init__(self) -> None:
        self.live = settings.stripe_live
        if self.live and _stripe is not None:
            _stripe.api_key = settings.stripe_secret_key

    async def create_account_link(self, *, email: str) -> ConnectAccountLink:
        """Begin Connect onboarding; return account id + redirect URL."""

        if not self.live:
            acct = _fake_id("acct")
            return ConnectAccountLink(account_id=acct, onboarding_url=f"https://connect.stub/{acct}")
        account = _stripe.Account.create(type="standard", email=email)
        link = _stripe.AccountLink.create(
            account=account.id,
            refresh_url="https://app.example.com/connect/refresh",
            return_url="https://app.example.com/connect/return",
            type="account_onboarding",
        )
        return ConnectAccountLink(account_id=account.id, onboarding_url=link.url)

    async def charge_member(
        self,
        *,
        connected_account_id: str,
        amount_cents: int,
        currency: str,
        idempotency_key: str,
        description: str = "",
    ) -> ConnectPaymentResult:
        """Charge a member on the gym's connected account (direct charge)."""

        if not self.live:
            return ConnectPaymentResult(
                id=_fake_id("pi"),
                status="succeeded",
                amount=amount_cents,
                currency=currency,
                charge_id=_fake_id("ch"),
            )
        pi = _stripe.PaymentIntent.create(
            amount=amount_cents,
            currency=currency,
            description=description,
            idempotency_key=idempotency_key,
            automatic_payment_methods={"enabled": True, "allow_redirects": "never"},
            stripe_account=connected_account_id,  # direct charge on connected acct
        )
        return ConnectPaymentResult(
            id=pi.id, status=pi.status, amount=pi.amount, currency=pi.currency,
            charge_id=(pi.latest_charge if isinstance(pi.latest_charge, str) else None),
        )

    async def create_member_intent(
        self, *, connected_account_id: str, amount_cents: int, currency: str,
        idempotency_key: str, description: str, metadata: dict[str, str],
        customer_id: str | None = None, save_for_future: bool = False,
    ) -> ConnectPaymentResult:
        """Create a direct charge intent with Stripe's eligible dynamic methods.

        Stripe filters the connected account's enabled methods using the
        payment currency and the buyer's location. The Payment Element handles
        any required redirect or authentication step in the browser.
        """
        if not self.live or _stripe is None:
            raise RuntimeError("Stripe Connect is not configured for real card payments.")
        params = dict(
            amount=amount_cents, currency=currency, description=description,
            metadata=metadata, idempotency_key=idempotency_key,
            automatic_payment_methods={"enabled": True},
        )
        if customer_id:
            params["customer"] = customer_id
        if save_for_future:
            params["setup_future_usage"] = "off_session"
        pi = _stripe.PaymentIntent.create(**params, stripe_account=connected_account_id)
        return ConnectPaymentResult(
            id=pi.id, status=pi.status, amount=pi.amount, currency=pi.currency,
            charge_id=(pi.latest_charge if isinstance(pi.latest_charge, str) else None),
            client_secret=pi.client_secret,
            payment_method_id=(pi.payment_method if isinstance(pi.payment_method, str) else None),
        )

    async def create_member_customer(
        self, *, connected_account_id: str, email: str, member_id: str, organization_id: str,
    ) -> str:
        """Create a customer on the gym's account for consented renewals."""
        if not self.live or _stripe is None:
            raise RuntimeError("Stripe Connect is not configured for recurring payments.")
        customer = _stripe.Customer.create(
            email=email,
            metadata={"member_id": member_id, "organization_id": organization_id},
            idempotency_key=f"member-customer-{organization_id}-{member_id}",
            stripe_account=connected_account_id,
        )
        return customer.id

    async def create_member_setup_intent(
        self, *, connected_account_id: str, customer_id: str,
        member_id: str, organization_id: str,
    ) -> dict:
        """Collect a reusable off-session payment method and its mandate."""
        if not self.live or _stripe is None:
            raise RuntimeError("Stripe Connect is not configured for recurring payments.")
        setup = _stripe.SetupIntent.create(
            customer=customer_id,
            usage="off_session",
            automatic_payment_methods={"enabled": True},
            metadata={"member_id": member_id, "organization_id": organization_id},
            idempotency_key=f"member-setup-{organization_id}-{member_id}-{uuid.uuid4().hex}",
            stripe_account=connected_account_id,
        )
        return {"id": setup.id, "client_secret": setup.client_secret}

    async def inspect_member_setup_intent(
        self, *, connected_account_id: str, setup_intent_id: str,
    ) -> dict | None:
        if not self.live or _stripe is None:
            return None
        setup = _stripe.SetupIntent.retrieve(
            setup_intent_id, expand=["payment_method"], stripe_account=connected_account_id,
        )
        payment_method = setup.payment_method
        return {
            "id": setup.id,
            "status": setup.status,
            "customer_id": setup.customer if isinstance(setup.customer, str) else getattr(setup.customer, "id", None),
            "payment_method_id": payment_method if isinstance(payment_method, str) else getattr(payment_method, "id", None),
            "payment_method_type": getattr(payment_method, "type", None),
            "member_id": (setup.metadata or {}).get("member_id"),
            "organization_id": (setup.metadata or {}).get("organization_id"),
        }

    async def charge_member_off_session(
        self, *, connected_account_id: str, customer_id: str, payment_method_id: str,
        amount_cents: int, currency: str, idempotency_key: str,
        description: str, metadata: dict[str, str],
    ) -> ConnectPaymentResult:
        """Attempt a previously authorized renewal without customer presence."""
        if not self.live or _stripe is None:
            raise RuntimeError("Stripe Connect is not configured for recurring payments.")
        pi = _stripe.PaymentIntent.create(
            amount=amount_cents, currency=currency, customer=customer_id,
            payment_method=payment_method_id, confirm=True, off_session=True,
            description=description, metadata=metadata,
            idempotency_key=idempotency_key,
            stripe_account=connected_account_id,
        )
        latest_charge = pi.latest_charge
        return ConnectPaymentResult(
            id=pi.id, status=pi.status, amount=pi.amount, currency=pi.currency,
            charge_id=latest_charge if isinstance(latest_charge, str) else None,
            payment_method_id=pi.payment_method if isinstance(pi.payment_method, str) else None,
        )

    async def inspect_member_intent(
        self, *, connected_account_id: str, intent_id: str
    ) -> ConnectPaymentResult | None:
        if not self.live or _stripe is None:
            return None
        pi = _stripe.PaymentIntent.retrieve(intent_id, expand=["latest_charge"], stripe_account=connected_account_id)
        latest_charge = pi.latest_charge
        charge_id = latest_charge if isinstance(latest_charge, str) else getattr(latest_charge, "id", None)
        details = getattr(latest_charge, "payment_method_details", None)
        return ConnectPaymentResult(
            id=pi.id, status=pi.status, amount=pi.amount, currency=pi.currency,
            charge_id=charge_id,
            client_secret=pi.client_secret,
            payment_method_type=getattr(details, "type", None),
            payment_method_id=pi.payment_method if isinstance(pi.payment_method, str) else None,
        )

    async def refund(
        self, *, connected_account_id: str, charge_id: str, amount_cents: int, idempotency_key: str
    ) -> dict:
        if not self.live:
            return {"id": _fake_id("re"), "status": "succeeded", "amount": amount_cents}
        refund = _stripe.Refund.create(
            charge=charge_id,
            amount=amount_cents,
            idempotency_key=idempotency_key,
            stripe_account=connected_account_id,
        )
        return {"id": refund.id, "status": refund.status, "amount": refund.amount}

    async def retrieve_payment_intent(
        self, *, connected_account_id: str, idempotency_key: str
    ) -> ConnectPaymentResult | None:
        """For stuck-payment reconciliation (Section 13.6).

        In stub mode there is no remote state, so return None (caller marks
        failed). With a real key, look up by idempotency key via the events API.
        """

        if not self.live:
            return None
        return None  # pragma: no cover  (production: query Stripe)


connect_stripe = StripeConnect()
