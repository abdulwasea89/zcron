"""Weekly recurring availability windows for gym trainers."""

from __future__ import annotations

from datetime import time

from sqlalchemy import CheckConstraint, Column, Time, UniqueConstraint
from sqlmodel import Field

from app.models.base import TimestampModel, UUIDModel


class TrainerAvailability(UUIDModel, TimestampModel, table=True):
    __tablename__ = "trainer_availability"
    __table_args__ = (
        CheckConstraint("weekday BETWEEN 0 AND 6", name="ck_trainer_availability_weekday"),
        CheckConstraint("start_time < end_time", name="ck_trainer_availability_time_range"),
        UniqueConstraint(
            "organization_id", "trainer_member_id", "weekday", "start_time", "end_time",
            name="uq_trainer_availability_window",
        ),
    )

    organization_id: str = Field(index=True, foreign_key="organizations.id")
    trainer_member_id: str = Field(index=True, foreign_key="organization_members.id")
    weekday: int
    start_time: time = Field(sa_column=Column(Time(), nullable=False))
    end_time: time = Field(sa_column=Column(Time(), nullable=False))
