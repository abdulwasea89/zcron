"""Request/response schemas for segmented campaigns (#39)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.constants import CampaignChannel


class CampaignCreateIn(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=2000)
    channel: CampaignChannel = Field(default=CampaignChannel.IN_APP)
    member_status: str | None = Field(default=None, max_length=120)
    plan_id: str | None = None
    min_days_since_last_visit: int | None = Field(default=None, ge=1, le=3650)
    scheduled_at: datetime | None = None
    send_limit: int = Field(default=200, ge=1, le=5000)


class CampaignScheduleIn(BaseModel):
    scheduled_at: datetime


class CampaignPreviewMember(BaseModel):
    member_id: str
    name: str
    email: str | None = None
    phone: str | None = None
    status: str


class CampaignPreviewOut(BaseModel):
    count: int
    sample: list[CampaignPreviewMember]


class CampaignOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    subject: str
    body: str
    channel: str
    status: str
    member_status: str | None = None
    plan_id: str | None = None
    min_days_since_last_visit: int | None = None
    scheduled_at: datetime | None = None
    sent_at: datetime | None = None
    send_limit: int
    sent_count: int


class CampaignListOut(CampaignOut):
    deliveries: int


class CampaignDeliveryOut(BaseModel):
    member_id: str
    member_name: str
    status: str
    channel: str
    delivered_at: datetime | None = None
    error: str | None = None


class CampaignDetailOut(CampaignOut):
    deliveries: list[CampaignDeliveryOut]


class CampaignRunOut(BaseModel):
    targeted: int
    sent: int
    suppressed: int
    failed: int
