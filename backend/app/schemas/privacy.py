from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class DataSubjectRequestCreate(BaseModel):
    member_id: str
    request_type: Literal["access", "export", "correction", "erasure"]
    note: str | None = Field(default=None, max_length=1000)


class DataSubjectRequestDecision(BaseModel):
    status: Literal["in_review", "completed", "rejected"]
    resolution_note: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def require_resolution(self):
        if self.status in {"completed", "rejected"} and not (self.resolution_note or "").strip():
            raise ValueError("Add a resolution note before closing a request.")
        return self


class DataSubjectRequestOut(BaseModel):
    id: str
    member_id: str
    member_name: str
    member_email: str
    request_type: str
    status: str
    note: str | None
    resolution_note: str | None
    erasure_redacted_at: datetime | None
    created_at: datetime
    resolved_at: datetime | None


class MemberMarketingConsentUpdate(BaseModel):
    email: bool
    sms: bool
    in_app: bool


class MemberMarketingConsentOut(BaseModel):
    member_id: str
    email: bool
    email_updated_at: datetime | None
    sms: bool
    sms_updated_at: datetime | None
    in_app: bool
    in_app_updated_at: datetime | None
