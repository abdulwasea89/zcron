"""Segmented marketing campaigns (#39).

The win-back engine (#36) is hard-wired to one audience (lapsed members) and
one offer. This module generalises that into the owner-authored campaign base:

* ``Campaign`` — a subject + body composed by the gym for a chosen audience and
  channel (in-app notification, email, or both), sent now or on a schedule.
  Audience criteria live inline: member status(es), an optional plan, and/or a
  minimum absence in days (reusing the attendance stream the inactivity ladder
  and streaks already read).
* ``CampaignDelivery`` — one row per (campaign, member). ``SENT`` exactly once
  thanks to a unique constraint, so resuming a partially-sent campaign (the
  scheduled worker or a manual re-run) never double-delivers.

Channel at scale: emails only go to verified addresses, and a per-run cap keeps
a stray press of "send" from blasting hundreds of messages at once.
"""

from __future__ import annotations

from datetime import datetime

from sqlmodel import Field, UniqueConstraint
from sqlalchemy import Column, JSON

from app.core.constants import (
    CampaignChannel,
    CampaignDeliveryStatus,
    CampaignStatus,
)
from app.models.base import TimestampModel, UUIDModel


class Campaign(UUIDModel, TimestampModel, table=True):
    __tablename__ = "campaigns"

    organization_id: str = Field(index=True, foreign_key="organizations.id")

    title: str
    subject: str                        # email subject / notification title
    body: str
    whatsapp_template_sid: str | None = None
    whatsapp_variables: dict[str, str] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    member_tag: str | None = None

    channel: CampaignChannel = Field(default=CampaignChannel.IN_APP, index=True)
    status: CampaignStatus = Field(default=CampaignStatus.DRAFT, index=True)

    # Audience criteria (resolved into the segment at send time).
    member_status: str | None = Field(default=None)   # comma-joined statuses
    plan_id: str | None = Field(default=None, foreign_key="membership_plans.id")
    min_days_since_last_visit: int | None = Field(default=None)

    scheduled_at: datetime | None = Field(default=None)
    sent_at: datetime | None = None
    send_limit: int = Field(default=200)
    sent_count: int = Field(default=0)

    created_by_user_id: str | None = Field(default=None, foreign_key="users.id")


class CampaignDelivery(UUIDModel, TimestampModel, table=True):
    """Per-member send record; 'SENT' once, thanks to the unique pair (#39)."""

    __tablename__ = "campaign_deliveries"
    __table_args__ = (
        UniqueConstraint("campaign_id", "member_id", name="uq_campaign_delivery_campaign_member"),
    )

    organization_id: str = Field(index=True, foreign_key="organizations.id")
    campaign_id: str = Field(index=True, foreign_key="campaigns.id")
    member_id: str = Field(index=True, foreign_key="organization_members.id")

    status: CampaignDeliveryStatus = Field(
        default=CampaignDeliveryStatus.PENDING, index=True
    )
    channel: CampaignChannel = Field(default=CampaignChannel.IN_APP)
    delivered_at: datetime | None = None
    error: str | None = None
    provider_message_id: str | None = Field(default=None, index=True)
    delivery_status: str | None = None
