"""Shared team inbox: member conversations across channels (Section 1.3, #20).

One thread per contact per channel, holding every inbound and outbound message,
who owns it, and its state. This is the shared inbox the front desk works from —
distinct from the AI assistant's own ``Conversation``/``ConversationMessage``
threads, which are per-staff chat with the model, not with members.

Tenant-scoped on both tables (Security Rule #1): the org filter is a plain column
predicate, no join needed. Unknown senders (a lead messaging before they are a
member) are supported: ``member_id`` is null and the thread is keyed on the
channel handle. When a handle matches a known member, we link it.
"""

from __future__ import annotations

from datetime import datetime

from sqlmodel import Field

from app.core.constants import (
    Channel,
    ConversationStatus,
    MessageDirection,
    SenderKind,
)
from app.models.base import TimestampModel, UUIDModel, utcnow


class InboxConversation(UUIDModel, TimestampModel, table=True):
    __tablename__ = "inbox_conversations"

    organization_id: str = Field(index=True, foreign_key="organizations.id")

    # Matched member, when the sender is recognised; null for unknown senders.
    member_id: str | None = Field(
        default=None, foreign_key="organization_members.id", index=True
    )

    channel: Channel = Field(default=Channel.OTHER, index=True)
    # Phone / email / @handle the conversation is keyed on.
    contact_handle: str = Field(index=True)
    contact_name: str | None = None

    subject: str | None = None
    status: ConversationStatus = Field(default=ConversationStatus.OPEN, index=True)
    # Staff owner; the "assign" action sets this.
    assigned_to: str | None = Field(default=None, foreign_key="users.id", index=True)

    last_message_at: datetime = Field(default_factory=utcnow, index=True)
    # Inbound messages the team has not read yet.
    unread_count: int = 0


class InboxMessage(UUIDModel, TimestampModel, table=True):
    __tablename__ = "inbox_messages"

    organization_id: str = Field(index=True, foreign_key="organizations.id")
    conversation_id: str = Field(index=True, foreign_key="inbox_conversations.id")

    direction: MessageDirection = Field(index=True)
    sender_kind: SenderKind = Field(index=True)
    # Staff/AI author; null for the contact's own messages.
    sender_user_id: str | None = Field(default=None, foreign_key="users.id")

    body: str = Field(default="")
    channel: Channel = Field(default=Channel.OTHER)

    # Provider message id (de-dupe on ingest) and the client idempotency key.
    external_id: str | None = Field(default=None, index=True)
    delivery_status: str | None = Field(default="received")
    delivery_error: str | None = None
    idempotency_key: str | None = Field(default=None, index=True)
