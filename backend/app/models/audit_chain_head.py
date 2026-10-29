"""Independent hash-chain heads for high-volume audit event lanes."""

from sqlalchemy import Column, String, UniqueConstraint
from sqlmodel import Field

from app.models.base import TimestampModel, UUIDModel


class AuditChainHead(UUIDModel, TimestampModel, table=True):
    __tablename__ = "audit_chain_heads"
    __table_args__ = (UniqueConstraint("organization_id", "chain_key"),)

    organization_id: str = Field(index=True)
    chain_key: str = Field(sa_column=Column(String(255), nullable=False))
    head_hash: str | None = Field(default=None, sa_column=Column(String(64), nullable=True))
