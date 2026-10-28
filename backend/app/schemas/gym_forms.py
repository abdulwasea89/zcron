"""Admin schemas for gym-authored forms and signed acceptance records."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class GymFormCreate(BaseModel):
    title: str = Field(min_length=2, max_length=160)
    form_type: Literal["waiver", "health"]
    body: str = Field(min_length=20, max_length=20000)

    @field_validator("title", "body")
    @classmethod
    def strip_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("This field is required.")
        return value


class GymFormOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    form_key: str
    title: str
    form_type: str
    version: int
    body: str
    active: bool
    created_at: datetime


class GymFormOption(BaseModel):
    id: str
    title: str
    form_type: str
    version: int


class GymFormAcceptanceOut(BaseModel):
    id: str
    member_id: str
    member_name: str | None = None
    form_title: str
    form_type: str
    form_version: int
    signed_by_name: str
    recorded_at: datetime
    collected_by: str
    evidence_filename: str
    evidence_media_type: str
    evidence_sha256: str
