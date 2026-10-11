"""Shared team inbox routes (Section 1.3, #20).

List/read/reply/assign/status plus an inbound ingest hook and an AI reply draft.
The inbox is conversation-with-members; the AI assistant's own chat threads live
under /assistant.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session, require_capability
from app.core.permissions import Capability
from app.core.tenancy import IDEMPOTENCY_HEADER, TenantContext
from app.schemas.inbox import (
    AssignCreate,
    ConversationDetail,
    ConversationSummary,
    DraftOut,
    InboundCreate,
    InboxStats,
    ReplyCreate,
    StatusCreate,
)
from app.services import inbox_service as inbox

router = APIRouter()


@router.get("/conversations", response_model=list[ConversationSummary])
async def list_conversations(
    status: str | None = None,
    channel: str | None = None,
    assigned_to: str | None = None,
    unassigned: bool = False,
    q: str | None = None,
    ctx: TenantContext = Depends(require_capability(Capability.VIEW_INBOX)),
    session: AsyncSession = Depends(get_session),
):
    return await inbox.list_conversations(
        session, org_id=ctx.org_id, status=status, channel=channel,
        assigned_to=assigned_to, unassigned=unassigned, q=q,
    )


@router.get("/stats", response_model=InboxStats)
async def stats(
    ctx: TenantContext = Depends(require_capability(Capability.VIEW_INBOX)),
    session: AsyncSession = Depends(get_session),
):
    return await inbox.inbox_stats(session, org_id=ctx.org_id, user_id=ctx.user_id)


@router.post("/conversations/ingest", response_model=ConversationDetail, status_code=201)
async def ingest(
    data: InboundCreate,
    ctx: TenantContext = Depends(require_capability(Capability.MANAGE_INBOX)),
    session: AsyncSession = Depends(get_session),
):
    """Store an inbound channel message (channel webhooks call this)."""

    return await inbox.record_inbound(
        session, org_id=ctx.org_id, channel=data.channel, handle=data.handle,
        body=data.body, contact_name=data.contact_name, member_id=data.member_id,
        external_id=data.external_id,
    )


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: str,
    ctx: TenantContext = Depends(require_capability(Capability.VIEW_INBOX)),
    session: AsyncSession = Depends(get_session),
):
    return await inbox.get_thread(session, org_id=ctx.org_id, conversation_id=conversation_id)


@router.post("/conversations/{conversation_id}/reply", response_model=ConversationDetail)
async def reply(
    conversation_id: str,
    data: ReplyCreate,
    idempotency_key: str = Header(default="", alias=IDEMPOTENCY_HEADER),
    ctx: TenantContext = Depends(require_capability(Capability.MANAGE_INBOX)),
    session: AsyncSession = Depends(get_session),
):
    return await inbox.reply(
        session, org_id=ctx.org_id, user_id=ctx.user_id, conversation_id=conversation_id,
        body=data.body, idempotency_key=idempotency_key or None,
    )


@router.post("/conversations/{conversation_id}/assign", response_model=ConversationDetail)
async def assign(
    conversation_id: str,
    data: AssignCreate,
    ctx: TenantContext = Depends(require_capability(Capability.MANAGE_INBOX)),
    session: AsyncSession = Depends(get_session),
):
    return await inbox.assign(
        session, org_id=ctx.org_id, conversation_id=conversation_id,
        user_id=data.user_id, actor_id=ctx.user_id,
    )


@router.post("/conversations/{conversation_id}/status", response_model=ConversationDetail)
async def set_status(
    conversation_id: str,
    data: StatusCreate,
    ctx: TenantContext = Depends(require_capability(Capability.MANAGE_INBOX)),
    session: AsyncSession = Depends(get_session),
):
    return await inbox.set_status(
        session, org_id=ctx.org_id, conversation_id=conversation_id,
        status=data.status, actor_id=ctx.user_id,
    )


@router.post("/conversations/{conversation_id}/draft", response_model=DraftOut)
async def draft(
    conversation_id: str,
    ctx: TenantContext = Depends(require_capability(Capability.MANAGE_INBOX)),
    session: AsyncSession = Depends(get_session),
):
    """AI-draft a reply to the thread's last inbound message."""

    body = await inbox.draft_reply(session, org_id=ctx.org_id, conversation_id=conversation_id)
    return DraftOut(body=body)
