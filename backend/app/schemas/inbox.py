"""Inbox schemas (Section 1.3, #20).

Conversation summary for the list, full thread for the detail pane, and the
small action payloads (reply, assign, status, ingest).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class InboundCreate(BaseModel):
    """An inbound channel message (a future webhook posts this)."""

    channel: str = "other"
    handle: str                  # phone / email / @handle
    body: str
    contact_name: str | None = None
    member_id: str | None = None
    external_id: str | None = None


class MessageOut(BaseModel):
    id: str
    direction: str
    sender_kind: str
    sender_user_id: str | None = None
    body: str
    channel: str
    delivery_status: str | None = None
    created_at: datetime


class ConversationSummary(BaseModel):
    id: str
    channel: str
    contact_handle: str
    contact_name: str | None = None
    member_id: str | None = None
    member_name: str | None = None
    subject: str | None = None
    status: str
    assigned_to: str | None = None
    assigned_name: str | None = None
    last_message_at: datetime
    unread_count: int
    preview: str | None = None
    preview_direction: str | None = None


class ConversationDetail(ConversationSummary):
    messages: list[MessageOut] = Field(default_factory=list)


class ReplyCreate(BaseModel):
    body: str


class AssignCreate(BaseModel):
    user_id: str | None = None   # null = unassign


class StatusCreate(BaseModel):
    status: str


class DraftOut(BaseModel):
    body: str


class InboxStats(BaseModel):
    open: int
    unassigned: int
    mine: int
    resolved: int
    unread: int
