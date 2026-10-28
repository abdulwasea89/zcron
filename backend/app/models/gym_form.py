"""Versioned gym-authored waivers and staff-collected signed copies."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, LargeBinary
from sqlmodel import Field, UniqueConstraint

from app.models.base import TimestampModel, UUIDModel


class GymForm(UUIDModel, TimestampModel, table=True):
    __tablename__ = "gym_forms"
    __table_args__ = (
        UniqueConstraint("organization_id", "form_key", "version", name="uq_gym_form_version"),
    )

    organization_id: str = Field(index=True, foreign_key="organizations.id")
    form_key: str = Field(index=True)
    title: str = Field(max_length=160)
    form_type: str = Field(max_length=24, index=True)
    version: int = Field(default=1)
    body: str
    active: bool = Field(default=True, index=True)
    created_by: str = Field(foreign_key="users.id")


class GymFormAcceptance(UUIDModel, TimestampModel, table=True):
    __tablename__ = "gym_form_acceptances"
    __table_args__ = (
        UniqueConstraint("organization_id", "member_id", "form_id", name="uq_gym_form_acceptance_member_version"),
    )

    organization_id: str = Field(index=True, foreign_key="organizations.id")
    member_id: str = Field(index=True, foreign_key="organization_members.id")
    form_id: str = Field(index=True, foreign_key="gym_forms.id")
    form_title: str = Field(max_length=160)
    form_type: str = Field(max_length=24)
    form_version: int
    form_body_snapshot: str
    signed_by_name: str = Field(max_length=160)
    recorded_at: datetime = Field(index=True)
    collected_by: str = Field(foreign_key="users.id")
    evidence_data: bytes = Field(sa_column=Column(LargeBinary, nullable=False))
    evidence_media_type: str = Field(max_length=32)
    evidence_filename: str = Field(max_length=180)
    evidence_sha256: str = Field(max_length=64, index=True)
