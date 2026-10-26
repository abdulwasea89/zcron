"""IdempotencyKey: dedup table for all state-changing requests (Section 13).

A client generates a UUID before sending. The server claims it (in_progress),
processes, then marks completed/failed and caches the response body. Replays with
the same key return the cached result; a different body with the same key is
rejected as tampered (Section 13.4).
"""

from __future__ import annotations

from datetime import datetime

from sqlmodel import Field
from sqlalchemy import Index, text

from app.core.constants import IdempotencyStatus
from app.models.base import TimestampModel, UUIDModel


class IdempotencyKey(UUIDModel, TimestampModel, table=True):
    __tablename__ = "idempotency_keys"

    key: str = Field(index=True)
    original_key: str | None = None
    organization_id: str | None = Field(default=None, index=True)
    user_id: str | None = None

    # Scope: method + path, so the same UUID can't cross endpoints.
    endpoint: str = ""
    request_hash: str = ""  # sha256 of the request body

    status: IdempotencyStatus = Field(default=IdempotencyStatus.IN_PROGRESS, index=True)
    response_code: int | None = None
    response_body: str | None = None

    completed_at: datetime | None = None

    __table_args__ = (Index(
        "uq_idempotency_scope_key", "key", "endpoint",
        text("coalesce(organization_id, '')"), text("coalesce(user_id, '')"), unique=True,
    ),)
