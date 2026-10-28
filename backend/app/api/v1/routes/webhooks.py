"""Stripe webhook endpoints (Section 17).

Two separate endpoints, each with its own signing secret (Security Rule #3 — the
platform and Connect accounts are never mixed):

  * POST /webhooks/stripe          — Platform (SaaS) events
  * POST /webhooks/stripe-connect  — Connect (member payment) events

Each verifies the ``Stripe-Signature`` header against the endpoint's secret
before trusting the payload, then routes by event type. In stub mode (no secret
configured) the raw JSON body is accepted so the flow is testable locally.
A handler error returns 400 so Stripe retries; a verification failure also 400.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.core.config import settings
from app.integrations.stripe_webhook import WebhookError, construct_event
from app.services import webhook_service
from app.services import idempotency_service

router = APIRouter()


@router.post("/stripe")
async def stripe_platform_webhook(
    request: Request,
    stripe_signature: str | None = Header(default=None, alias="Stripe-Signature"),
    session: AsyncSession = Depends(get_session),
):
    payload = await request.body()
    try:
        event = construct_event(payload, stripe_signature, secret=settings.stripe_webhook_secret)
    except WebhookError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid webhook: {exc}")
    event_id = event.get("id")
    claim = None
    if event_id:
        claim = await idempotency_service.claim(
            session, key=event_id, endpoint="stripe/platform-webhook", body=event,
        )
        if not claim.claimed:
            return JSONResponse(
                json.loads(claim.cached_response or "{}"),
                status_code=claim.cached_code or 200,
            )
    result = await webhook_service.handle_platform_event(session, event)
    if claim:
        await idempotency_service.complete(
            session, claim.record, code=200, body=json.dumps(result),
        )
    return result


@router.post("/stripe-connect")
async def stripe_connect_webhook(
    request: Request,
    stripe_signature: str | None = Header(default=None, alias="Stripe-Signature"),
    session: AsyncSession = Depends(get_session),
):
    payload = await request.body()
    try:
        event = construct_event(
            payload, stripe_signature, secret=settings.stripe_connect_webhook_secret
        )
    except WebhookError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid webhook: {exc}")
    return await webhook_service.handle_connect_event(session, event)
