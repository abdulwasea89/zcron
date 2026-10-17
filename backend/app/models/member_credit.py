"""Tenant/member/currency scoped credit balances and immutable journal entries."""
from sqlalchemy import UniqueConstraint
from sqlmodel import Field
from app.models.base import UUIDModel, TimestampModel


class MemberCreditAccount(UUIDModel, TimestampModel, table=True):
    __tablename__ = "member_credit_accounts"
    __table_args__ = (UniqueConstraint("organization_id", "member_id", "currency"),)
    organization_id: str = Field(foreign_key="organizations.id", index=True)
    member_id: str = Field(foreign_key="organization_members.id", index=True)
    currency: str
    balance_minor: int = 0


class MemberCreditEntry(UUIDModel, TimestampModel, table=True):
    __tablename__ = "member_credit_entries"
    account_id: str = Field(foreign_key="member_credit_accounts.id", index=True)
    reference: str = Field(unique=True, index=True)
    amount_minor: int
    description: str
