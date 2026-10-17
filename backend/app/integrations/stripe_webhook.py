"""Stripe webhook signature verification with a stub fallback (Section 17).

Each webhook endpoint verifies the Stripe signature before trusting the payload
(CLAUDE.md "Webhook Endpoints"). When a signing secret is configured and the
``stripe`` SDK is present, ``construct_event`` enforces the HMAC signature and
timestamp. When no secret is configured (local/dev/stub mode), the raw JSON body
is parsed directly so the webhook flow is runnable end-to-end without Stripe.

Raises ``WebhookError`` on a bad signature / malformed payload; the route maps it
to a 400 so Stripe will retry.
"""

from __future__ import annotations

import json

from app.core.config import settings

try:
    import stripe as _stripe
except Exception:  # pragma: no cover
    _stripe = None


class WebhookError(Exception):
    """Raised when a webhook payload can't be verified or parsed."""


def construct_event(payload: bytes, sig_header: str | None, *, secret: str) -> dict:
    """Return the verified event as a dict.

    Live mode (real Stripe key + signing secret + SDK): verify the signature.
    Stub mode (no real key configured): parse the JSON body directly so the
    webhook flow is runnable locally — consistent with the other Stripe
    integrations, which all gate on ``settings.stripe_live``.
    """

    if settings.stripe_live:
        if not secret:
            raise WebhookError("Stripe webhook signing secret is not configured.")
        if _stripe is None:
            raise WebhookError("Stripe SDK is unavailable.")
        try:
            event = _stripe.Webhook.construct_event(payload, sig_header or "", secret)
        except Exception as exc:  # signature/timestamp/JSON failure
            raise WebhookError(str(exc)) from exc
        # Normalise to a plain dict regardless of SDK return type.
        return event if isinstance(event, dict) else json.loads(str(event))

    # Stub mode: no secret configured -> trust the local payload.
    try:
        return json.loads(payload.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise WebhookError("Malformed webhook payload.") from exc
