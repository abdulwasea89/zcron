"""Staff-managed record of member privacy requests."""

from __future__ import annotations

from datetime import datetime

from sqlmodel import Field
from sqlalchemy import Column, JSON

from app.models.base import TimestampModel, UUIDModel


class DataSubjectRequest(UUIDModel, TimestampModel, table=True):
    __tablename__ = "data_subject_requests"

    organization_id: str = Field(index=True, foreign_key="organizations.id")
    # Keep the request record even if the organization later removes the member.
    member_id: str = Field(index=True)
    member_name: str
    member_email: str
    request_type: str = Field(index=True)  # access, export, correction, erasure
    status: str = Field(default="open", index=True)  # open, in_review, completed, rejected
    note: str | None = None
    resolution_note: str | None = None
    erasure_redacted_at: datetime | None = None
    review_checks: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    created_by: str = Field(foreign_key="users.id")
    resolved_by: str | None = Field(default=None, foreign_key="users.id")
    resolved_at: datetime | None = None
