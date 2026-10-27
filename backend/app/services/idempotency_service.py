"""Server-side idempotency (Section 13).

Implements the claim/replay protocol for state-changing requests:

  * ``claim`` — first time a key is seen, insert an ``in_progress`` row and
    return CLAIMED. If the key exists: completed -> return cached response;
    in_progress -> 409 Conflict; failed -> return cached failure. A matching key
    with a *different* request body is rejected as tampered (Section 13.4).
  * ``complete`` / ``fail`` — record the outcome + cached response body.

This is the single mechanism behind "zero double-charge". Stripe is also passed
the same key (Section 13.5) as a second layer.
"""

from __future__ import annotations

from dataclasses import dataclass
import json

from fastapi import HTTPException, status
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.constants import IdempotencyStatus
from app.core.security import now_utc
from app.models.idempotency_key import IdempotencyKey
from app.utils.idempotency import hash_request_body


@dataclass
class ClaimResult:
    claimed: bool                 # True -> caller should do the work
    record: IdempotencyKey
    cached_response: str | None = None
    cached_code: int | None = None


async def claim(
    session: AsyncSession,
    *,
    key: str,
    endpoint: str,
    body,
    organization_id: str | None = None,
    user_id: str | None = None,
) -> ClaimResult:
    if not key:
        raise HTTPException(status_code=400, detail="Idempotency-Key header is required.")
    if len(key) > 512:
        raise HTTPException(status_code=400, detail="Idempotency-Key must be 512 characters or fewer.")

    request_hash = hash_request_body(body)
    organization_id = organization_id or None
    user_id = user_id or None
    statement = select(IdempotencyKey).where(
        IdempotencyKey.key == key, IdempotencyKey.endpoint == endpoint,
        IdempotencyKey.organization_id == organization_id, IdempotencyKey.user_id == user_id,
    )

    def replay(existing: IdempotencyKey) -> ClaimResult:
        # Same key, different body -> replay attack with modified params.
        if existing.request_hash != request_hash:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Idempotency key reused with a different request body.",
            )
        if existing.status == IdempotencyStatus.COMPLETED:
            return ClaimResult(False, existing, existing.response_body, existing.response_code)
        if existing.status == IdempotencyStatus.IN_PROGRESS:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Request already in progress. Retry shortly.",
            )
        if existing.status == IdempotencyStatus.FAILED:
            detail = "The previous request failed. Review its status before retrying."
            try:
                body = json.loads(existing.response_body or "{}")
                if isinstance(body, dict) and isinstance(body.get("detail"), (str, list, dict)):
                    detail = body["detail"]
            except (TypeError, ValueError):
                pass
            code = existing.response_code or 409
            raise HTTPException(status_code=code if 400 <= code < 600 else 409, detail=detail)
        raise HTTPException(status_code=409, detail="Request status is unavailable. Retry shortly.")

    existing = (await session.execute(statement)).scalar_one_or_none()
    if existing is not None:
        return replay(existing)

    record = IdempotencyKey(
        key=key,
        endpoint=endpoint,
        request_hash=request_hash,
        organization_id=organization_id,
        user_id=user_id,
        status=IdempotencyStatus.IN_PROGRESS,
    )
    dialect = session.get_bind().dialect.name
    insert = postgres_insert if dialect == "postgresql" else sqlite_insert if dialect == "sqlite" else None
    if insert is None:
        raise RuntimeError("Idempotency claims require PostgreSQL or SQLite.")
    claimed = (await session.execute(
        insert(IdempotencyKey).values(**record.model_dump()).on_conflict_do_nothing().returning(IdempotencyKey)
    )).scalar_one_or_none()
    if claimed is not None:
        return ClaimResult(True, claimed)
    # A concurrent request won the unique claim without aborting this transaction.
    existing = (await session.execute(statement)).scalar_one_or_none()
    if existing is None:
        raise HTTPException(status_code=409, detail="Request is being claimed. Retry shortly.")
    return replay(existing)


async def complete(
    session: AsyncSession, record: IdempotencyKey, *, code: int, body: str
) -> None:
    record.status = IdempotencyStatus.COMPLETED
    record.response_code = code
    record.response_body = body
    record.completed_at = now_utc()
    session.add(record)


async def fail(
    session: AsyncSession, record: IdempotencyKey, *, code: int, body: str
) -> None:
    record.status = IdempotencyStatus.FAILED
    record.response_code = code
    record.response_body = body
    record.completed_at = now_utc()
    session.add(record)
