from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class InboxChannelConnectIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    credentials: dict[str, Any] = Field(min_length=1)


class InboxChannelConnectionOut(BaseModel):
    channel: str
    connected: bool
    connected_at: datetime | None = None
    webhook_url: str | None = None
