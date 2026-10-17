"""Encrypted per-workspace credentials for shared inbox channels."""

from __future__ import annotations

from datetime import datetime

from sqlmodel import Field, UniqueConstraint

from app.models.base import TimestampModel, UUIDModel, utcnow


class InboxChannelConnection(UUIDModel, TimestampModel, table=True):
    __tablename__ = "inbox_channel_connections"
    __table_args__ = (
        UniqueConstraint("organization_id", "channel", name="uq_inbox_channel_org_channel"),
    )

    organization_id: str = Field(index=True, foreign_key="organizations.id")
    channel: str = Field(index=True)
    credentials_ciphertext: str
    webhook_token: str | None = None
    connected_at: datetime = Field(default_factory=utcnow, index=True)
