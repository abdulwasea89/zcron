"""Granted personal-training session credits."""

from datetime import datetime
from sqlalchemy import CheckConstraint
from sqlmodel import Field

from app.models.base import TimestampModel, UUIDModel, utcnow


class TrainerPackage(UUIDModel, TimestampModel, table=True):
    __tablename__ = "trainer_packages"
    __table_args__ = (
        CheckConstraint("total_sessions > 0", name="ck_trainer_package_total_positive"),
        CheckConstraint("used_sessions >= 0 AND used_sessions <= total_sessions", name="ck_trainer_package_usage_range"),
    )

    organization_id: str = Field(index=True, foreign_key="organizations.id")
    member_id: str = Field(index=True, foreign_key="organization_members.id")
    trainer_member_id: str = Field(index=True, foreign_key="organization_members.id")
    granted_by_user_id: str = Field(foreign_key="users.id")
    name: str
    total_sessions: int
    used_sessions: int = 0
    granted_at: datetime = Field(default_factory=utcnow)
    expires_at: datetime | None = None
    cancelled_at: datetime | None = None
