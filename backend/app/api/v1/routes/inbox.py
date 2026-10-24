"""Shared team inbox routes (Section 1.3, #20).

List/read/reply/assign/status plus an inbound ingest hook and an AI reply draft.
The inbox is conversation-with-members; the AI assistant's own chat threads live
under /assistant.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from jose import jwt
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.api.deps import get_session, require_capability
from app.core.constants import LeadSource
from app.core.permissions import Capability
from app.core.tenancy import IDEMPOTENCY_HEADER, TenantContext
from app.core.config import settings
from app.core.rate_limit import rate_limiter
from app.core.security import safe_decode
from app.models.inbox import InboxConversation
from app.models.lead import Lead
from app.models.organization import Organization
from app.schemas.leads import LeadCreate
from app.services.inbox_channels_service import get_credentials
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
from app.services import inbox_service as inbox, leads_service

router = APIRouter()


class PublicChatStart(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3, max_length=254)
    message: str = Field(min_length=1, max_length=4000)


class PublicChatMessage(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


def _chat_token(conversation_id: str, org_id: str) -> str:
    return jwt.encode({"sub": conversation_id, "org_id": org_id, "type": "inbox_web_chat", "exp": datetime.now(timezone.utc) + timedelta(days=2)}, settings.secret_key, algorithm=settings.jwt_algorithm)


def _chat_claims(token: str | None) -> dict:
    claims = safe_decode(token or "")
    if not claims or claims.get("type") != "inbox_web_chat" or not claims.get("sub") or not claims.get("org_id"):
        raise HTTPException(status_code=401, detail="This chat session has expired. Start a new conversation.")
    return claims


async def _public_chat_thread(session: AsyncSession, conversation_id: str) -> dict:
    conv = await session.get(InboxConversation, conversation_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="Chat conversation not found.")
    thread = await inbox._thread_out(session, conversation_id)
    return {"id": conv.id, "status": thread["status"], "messages": [
        {"id": m["id"], "direction": m["direction"], "body": m["body"], "created_at": m["created_at"]}
        for m in thread["messages"]
    ]}


@router.get("/public/{org_code}")
async def public_chat_info(org_code: str, session: AsyncSession = Depends(get_session)):
    org = (await session.execute(select(Organization).where(Organization.org_code == org_code))).scalar_one_or_none()
    if org is None or not (await get_credentials(session, org.id, "web_chat")):
        raise HTTPException(status_code=404, detail="This workspace has not enabled web chat.")
    return {"organization_name": org.name, "accent_color": org.accent_color}


@router.post("/public/{org_code}/conversations", status_code=201)
async def public_chat_start(org_code: str, data: PublicChatStart, request: Request, session: AsyncSession = Depends(get_session)):
    if not data.name.strip() or not data.message.strip() or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", data.email.strip()):
        raise HTTPException(status_code=422, detail="Enter your name, a valid email address, and a message.")
    ip = request.client.host if request.client else "unknown"
    allowed, _ = await rate_limiter.hit(f"inbox-chat:{org_code}:{ip}", 8, 60)
    if not allowed:
        raise HTTPException(status_code=429, detail="Please wait a moment before sending another message.")
    org = (await session.execute(select(Organization).where(Organization.org_code == org_code))).scalar_one_or_none()
    if org is None or not (await get_credentials(session, org.id, "web_chat")):
        raise HTTPException(status_code=404, detail="This workspace has not enabled web chat.")
    handle = data.email.strip().lower()
    thread = await inbox.record_inbound(session, org_id=org.id, channel="web_chat", handle=handle, body=data.message.strip(), contact_name=data.name.strip(), force_new=True)
    if not thread.get("member_id"):
        lead = (await session.execute(select(Lead).where(
            Lead.organization_id == org.id, Lead.email == handle,
        ).limit(1))).scalar_one_or_none()
        if lead is None:
            await leads_service.create_lead(
                session, org_id=org.id, actor_id=None,
                data=LeadCreate(name=data.name.strip(), email=handle, source=LeadSource.WEB_FORM),
            )
    await inbox.record_web_chat_ack(
        session, org_id=org.id, conversation_id=thread["id"],
        body=f"Thanks for contacting {org.name}. Your message is in the team's inbox, and someone will follow up as soon as they are available.",
    )
    token = _chat_token(thread["id"], org.id)
    return {"token": token, "thread": await _public_chat_thread(session, thread["id"])}


@router.get("/public/conversations/{conversation_id}")
async def public_chat_read(conversation_id: str, authorization: str | None = Header(default=None), session: AsyncSession = Depends(get_session)):
    claims = _chat_claims(authorization.removeprefix("Bearer ") if authorization else None)
    if claims["sub"] != conversation_id:
        raise HTTPException(status_code=403, detail="Chat session does not match this conversation.")
    conv = await session.get(InboxConversation, conversation_id)
    if conv is None or conv.organization_id != claims["org_id"] or inbox._value(conv.channel) != "web_chat":
        raise HTTPException(status_code=404, detail="Chat conversation not found.")
    return await _public_chat_thread(session, conversation_id)


@router.post("/public/conversations/{conversation_id}/messages", status_code=201)
async def public_chat_message(conversation_id: str, data: PublicChatMessage, request: Request, authorization: str | None = Header(default=None), session: AsyncSession = Depends(get_session)):
    if not data.message.strip():
        raise HTTPException(status_code=422, detail="Write a message before sending.")
    claims = _chat_claims(authorization.removeprefix("Bearer ") if authorization else None)
    if claims["sub"] != conversation_id:
        raise HTTPException(status_code=403, detail="Chat session does not match this conversation.")
    ip = request.client.host if request.client else "unknown"
    allowed, _ = await rate_limiter.hit(f"inbox-chat-send:{conversation_id}:{ip}", 12, 60)
    if not allowed:
        raise HTTPException(status_code=429, detail="Please wait a moment before sending another message.")
    conv = await session.get(InboxConversation, conversation_id)
    if conv is None or conv.organization_id != claims["org_id"] or inbox._value(conv.channel) != "web_chat":
        raise HTTPException(status_code=404, detail="Chat conversation not found.")
    await inbox.record_inbound(session, org_id=conv.organization_id, channel="web_chat", handle=conv.contact_handle, body=data.message.strip(), contact_name=conv.contact_name)
    return await _public_chat_thread(session, conversation_id)


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


@router.post("/conversations/{conversation_id}/messages/{message_id}/retry", response_model=ConversationDetail)
async def retry_reply_delivery(
    conversation_id: str,
    message_id: str,
    ctx: TenantContext = Depends(require_capability(Capability.MANAGE_INBOX)),
    session: AsyncSession = Depends(get_session),
):
    return await inbox.retry_delivery(
        session, org_id=ctx.org_id, conversation_id=conversation_id, message_id=message_id,
        actor_id=ctx.user_id,
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
