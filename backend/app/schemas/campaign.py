"""Request/response schemas for segmented campaigns (#39)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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
    whatsapp_template_sid: str | None = Field(default=None, pattern=r"^HX[0-9a-fA-F]{32}$")
    whatsapp_variables: dict[str, str] = Field(default_factory=dict, max_length=10)
    member_tag: str | None = Field(default=None, min_length=1, max_length=32)

    @field_validator("whatsapp_variables")
    @classmethod
    def validate_template_variables(cls, values):
        if any(key not in {str(index) for index in range(1, 100)} or len(value) > 500
               or any(character in value for character in "\n\r\t") for key, value in values.items()):
            raise ValueError("Use numbered template variables (1–99), at most 500 characters, without line breaks or tabs.")
        return values

    @field_validator("member_tag")
    @classmethod
    def normalize_tag(cls, value):
        if value is not None and not value.strip():
            raise ValueError("Enter a member tag or leave it empty.")
        return value.strip().casefold() if value else value

    @model_validator(mode="after")
    def require_whatsapp_template(self):
        if self.channel == CampaignChannel.WHATSAPP and not self.whatsapp_template_sid:
            raise ValueError("WhatsApp campaigns require an approved Twilio Content SID.")
        if self.channel != CampaignChannel.WHATSAPP and (self.whatsapp_template_sid or self.whatsapp_variables):
            raise ValueError("WhatsApp template fields require the WhatsApp channel.")
        return self


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
    whatsapp_template_sid: str | None = None
    whatsapp_variables: dict[str, str] = Field(default_factory=dict)
    member_tag: str | None = None


class CampaignListOut(CampaignOut):
    deliveries: int


class CampaignDeliveryOut(BaseModel):
    member_id: str
    member_name: str
    status: str
    channel: str
    delivered_at: datetime | None = None
    delivery_status: str | None = None
    error: str | None = None


class CampaignDetailOut(CampaignOut):
    deliveries: list[CampaignDeliveryOut]


class CampaignRunOut(BaseModel):
    targeted: int
    sent: int
    suppressed: int
    failed: int
