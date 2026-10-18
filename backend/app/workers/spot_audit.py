"""Weekly spot-audit job for auto-approved receipts (Section 10.5).

Picks ~5% of auto-approved receipts that were flagged for audit and surfaces
them to the admin queue. Deterministic selection happened at scoring time
(``spot_audit_selected``); this job simply collects them for review and tracks
the weekly reversal rate used to tune the auto-approve threshold (Section 10.6).

Runnable inline (no Celery broker needed) for local dev/tests.
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer
from sqlmodel import select

from app.core.constants import ReceiptStatus
from app.core.security import now_utc
from app.models.receipt import ReceiptUpload
from app.services.audit_service import record_audit


async def collect_spot_audits(session: AsyncSession, *, org_id: str) -> list[ReceiptUpload]:
    """Return auto-approved receipts selected for spot audit in this org."""

    return list(
        (
            await session.execute(
                select(ReceiptUpload).options(defer(ReceiptUpload.image_data)).where(
                    ReceiptUpload.organization_id == org_id,
                    ReceiptUpload.status == ReceiptStatus.AUTO_APPROVED,
                    ReceiptUpload.spot_audit_selected == True,  # noqa: E712
                ).order_by(ReceiptUpload.created_at)
            )
        ).scalars()
    )


async def weekly_reversal_rate(session: AsyncSession, *, org_id: str) -> float:
    """Reversal rate on auto-approved receipts over the last 7 days (Section 10.6).

    Used to tune the auto-approve threshold: > 2% raise, < 0.2% (with backlog)
    lower. Returns a fraction 0..1.
    """

    cutoff = now_utc() - timedelta(days=7)
    rows = (
        await session.execute(
            select(ReceiptUpload).options(defer(ReceiptUpload.image_data)).where(
                ReceiptUpload.organization_id == org_id,
                ReceiptUpload.created_at >= cutoff,
                ReceiptUpload.auto_approved == True,  # noqa: E712
            )
        )
    ).scalars()
    total = 0
    reversed_count = 0
    for r in rows:
        total += 1
        if r.status == ReceiptStatus.REVERSED:
            reversed_count += 1
    return (reversed_count / total) if total else 0.0


async def run_spot_audit(session: AsyncSession, *, org_id: str) -> dict:
    """Entry point: report selected audits + current reversal rate."""

    selected = await collect_spot_audits(session, org_id=org_id)
    rate = await weekly_reversal_rate(session, org_id=org_id)
    await record_audit(session, action="receipt.spot_audit_run", organization_id=org_id,
                       metadata={"selected": len(selected), "reversal_rate": rate})
    return {"selected": [r.id for r in selected], "reversal_rate": rate}
