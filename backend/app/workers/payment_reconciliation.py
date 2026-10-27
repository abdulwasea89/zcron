"""Report stale payment requests without inventing a provider outcome."""

from __future__ import annotations

from datetime import timedelta
import logging

from sqlalchemy import or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.config import settings
from app.core.constants import IdempotencyStatus
from app.core.security import now_utc
from app.models.idempotency_key import IdempotencyKey


async def reconcile_stuck(session: AsyncSession, *, org_id: str | None = None) -> dict:
    """Count stale payment claims for operator review; keep their state intact."""

    cutoff = now_utc() - timedelta(seconds=settings.idempotency_stuck_seconds)
    stmt = select(IdempotencyKey).where(
        IdempotencyKey.status == IdempotencyStatus.IN_PROGRESS,
        IdempotencyKey.created_at < cutoff,
        or_(IdempotencyKey.endpoint.in_(["cash.log", "POST /memberships/pay", "POST /payments/refund",
                                        "POST /invoices/{id}/record-payment"]),
            IdempotencyKey.endpoint.like("gym-invoice-payment:%")),
    )
    if org_id is not None:
        stmt = stmt.where(IdempotencyKey.organization_id == org_id)

    stuck = list((await session.execute(stmt)).scalars())
    if stuck:
        logging.warning("%s stale payment requests need manual reconciliation; no provider outcome was inferred", len(stuck))
    # shortcut: provider lookup and replay repair are not implemented; keep claims pending until a verified recovery flow exists.
    return {"checked": len(stuck), "resolved_succeeded": 0, "resolved_failed": 0, "unresolved": len(stuck)}
