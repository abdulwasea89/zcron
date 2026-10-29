"""AuditLog: every state change, for disputes and security (Security Rule #10)."""

from __future__ import annotations

from sqlalchemy import Column, String
from sqlmodel import Field

from app.models.base import TimestampModel, UUIDModel


class AuditLog(UUIDModel, TimestampModel, table=True):
    __tablename__ = "audit_logs"

    organization_id: str | None = Field(default=None, index=True)
    actor_user_id: str | None = Field(default=None, index=True)
    action: str = Field(index=True)
    entity_type: str | None = None
    entity_id: str | None = Field(default=None, index=True)
    old_values_json: str | None = None
    new_values_json: str | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    metadata_json: str | None = None
    previous_hash: str | None = Field(default=None, sa_column=Column(String(64), nullable=True))
    entry_hash: str | None = Field(default=None, sa_column=Column(String(64), nullable=True, index=True))
    chain_key: str | None = Field(default=None, index=True)
