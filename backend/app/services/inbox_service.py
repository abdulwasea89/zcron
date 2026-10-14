"""Shared team inbox service (Section 1.3, #20).

Conversations and messages across channels, with matching to members, assignment,
status, and an AI reply draft. No channel provider is wired yet: inbound messages
arrive through ``record_inbound`` (a future webhook calls it), and outbound
replies are stored and marked ``sent`` (a future sender dispatches them).
"""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import and_, case, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.constants import (
    Channel,
    ConversationStatus,
    MessageDirection,
    SenderKind,
)
from app.core.security import now_utc
from app.models.inbox import InboxConversation, InboxMessage
from app.models.membership import OrganizationMember
from app.models.user import User
from app.realtime import events
from app.services.audit_service import record_audit


def _value(v) -> str:
    return v.value if hasattr(v, "value") else str(v)


def _enum(enum_cls, value, default):
    try:
        return enum_cls(value)
    except (ValueError, KeyError):
        return default


async def _match_member(session: AsyncSession, org_id: str, handle: str) -> str | None:
    """Link a channel handle to a member by email or phone (best effort)."""

    h = handle.strip().lower()
    if not h:
        return None
    row = (
        await session.execute(
            select(OrganizationMember.id)
            .join(User, User.id == OrganizationMember.user_id)
            .where(
                OrganizationMember.organization_id == org_id,
                or_(func.lower(User.email) == h, OrganizationMember.phone == handle.strip()),
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    return row


async def _get_conversation(
    session: AsyncSession, org_id: str, conversation_id: str
) -> InboxConversation:
    conv = await session.get(InboxConversation, conversation_id)
    if conv is None or conv.organization_id != org_id:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return conv


async def find_or_create(
    session: AsyncSession,
    *,
    org_id: str,
    channel: Channel,
    handle: str,
    contact_name: str | None = None,
) -> InboxConversation:
    """An open thread for this (channel, handle), or a new one."""

    conv = (
        await session.execute(
            select(InboxConversation)
            .where(
                InboxConversation.organization_id == org_id,
                InboxConversation.channel == channel,
                InboxConversation.contact_handle == handle,
                InboxConversation.status != ConversationStatus.RESOLVED,
            )
            .order_by(InboxConversation.last_message_at.desc())
            .limit(1)
        )
    ).scalars().first()
    if conv is not None:
        if contact_name and not conv.contact_name:
            conv.contact_name = contact_name
            session.add(conv)
        return conv

    conv = InboxConversation(
        organization_id=org_id,
        channel=channel,
        contact_handle=handle,
        contact_name=contact_name,
    )
    session.add(conv)
    await session.flush()
    return conv


async def record_inbound(
    session: AsyncSession,
    *,
    org_id: str,
    channel: str | Channel,
    handle: str,
    body: str,
    contact_name: str | None = None,
    member_id: str | None = None,
    external_id: str | None = None,
) -> dict:
    """Store an inbound message, creating/ropening its conversation."""

    ch = _enum(Channel, channel, Channel.OTHER)

    # Idempotent on the provider's message id.
    if external_id:
        existing = (
            await session.execute(
                select(InboxMessage).where(
                    InboxMessage.organization_id == org_id,
                    InboxMessage.external_id == external_id,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return await _thread_out(session, existing.conversation_id)

    conv = await find_or_create(
        session, org_id=org_id, channel=ch, handle=handle, contact_name=contact_name
    )
    if conv.member_id is None:
        conv.member_id = member_id or await _match_member(session, org_id, handle)
    # A new inbound reopens a resolved thread.
    if conv.status == ConversationStatus.RESOLVED:
        conv.status = ConversationStatus.OPEN
    conv.last_message_at = now_utc()
    conv.unread_count = conv.unread_count + 1
    session.add(conv)

    session.add(
        InboxMessage(
            organization_id=org_id,
            conversation_id=conv.id,
            direction=MessageDirection.INBOUND,
            sender_kind=SenderKind.CONTACT,
            body=body,
            channel=ch,
            external_id=external_id,
            delivery_status="received",
        )
    )
    await session.flush()
    from app.services.members_service import detect_freeze_request_from_message

    await detect_freeze_request_from_message(
        session, org_id=org_id, member_id=conv.member_id, body=body,
    )
    await record_audit(
        session, action="inbox.received", organization_id=org_id,
        entity_type="inbox_conversation", entity_id=conv.id,
        metadata={"channel": ch.value, "handle": handle},
    )
    await events.inbox_changed(org_id, conversation_id=conv.id, action="received")
    return await _thread_out(session, conv.id)


async def reply(
    session: AsyncSession,
    *,
    org_id: str,
    user_id: str,
    conversation_id: str,
    body: str,
    idempotency_key: str | None = None,
) -> dict:
    """Send a staff reply (idempotent) and take ownership if unassigned."""

    conv = await _get_conversation(session, org_id, conversation_id)

    if idempotency_key:
        existing = (
            await session.execute(
                select(InboxMessage).where(
                    InboxMessage.organization_id == org_id,
                    InboxMessage.idempotency_key == idempotency_key,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return await _thread_out(session, conv.id)

    session.add(
        InboxMessage(
            organization_id=org_id,
            conversation_id=conv.id,
            direction=MessageDirection.OUTBOUND,
            sender_kind=SenderKind.STAFF,
            sender_user_id=user_id,
            body=body,
            channel=conv.channel,
            idempotency_key=idempotency_key,
        )
    )
    conv.last_message_at = now_utc()
    if conv.assigned_to is None:
        conv.assigned_to = user_id
    if conv.status == ConversationStatus.OPEN:
        conv.status = ConversationStatus.PENDING
    session.add(conv)
    await session.flush()
    await record_audit(
        session, action="inbox.replied", organization_id=org_id, actor_user_id=user_id,
        entity_type="inbox_conversation", entity_id=conv.id,
    )
    await events.inbox_changed(org_id, conversation_id=conv.id, action="replied")
    return await _thread_out(session, conv.id)


async def assign(
    session: AsyncSession, *, org_id: str, conversation_id: str, user_id: str | None, actor_id: str
) -> dict:
    conv = await _get_conversation(session, org_id, conversation_id)
    if user_id is not None:
        target = await session.get(User, user_id)
        membership = (
            await session.execute(
                select(OrganizationMember).where(
                    OrganizationMember.organization_id == org_id,
                    OrganizationMember.user_id == user_id,
                )
            )
        ).scalar_one_or_none()
        if target is None or membership is None:
            raise HTTPException(status_code=404, detail="Staff member not found in this org.")
    conv.assigned_to = user_id
    session.add(conv)
    await record_audit(
        session, action="inbox.assigned", organization_id=org_id, actor_user_id=actor_id,
        entity_type="inbox_conversation", entity_id=conv.id,
        metadata={"assigned_to": user_id},
    )
    await events.inbox_changed(org_id, conversation_id=conv.id, action="assigned")
    return await _thread_out(session, conv.id)


async def set_status(
    session: AsyncSession, *, org_id: str, conversation_id: str, status: str, actor_id: str
) -> dict:
    conv = await _get_conversation(session, org_id, conversation_id)
    conv.status = _enum(ConversationStatus, status, ConversationStatus.OPEN)
    session.add(conv)
    await record_audit(
        session, action="inbox.status_changed", organization_id=org_id, actor_user_id=actor_id,
        entity_type="inbox_conversation", entity_id=conv.id,
        metadata={"status": conv.status.value},
    )
    await events.inbox_changed(org_id, conversation_id=conv.id, action="status")
    return await _thread_out(session, conv.id)


async def mark_read(session: AsyncSession, *, org_id: str, conversation_id: str) -> None:
    conv = await _get_conversation(session, org_id, conversation_id)
    if conv.unread_count:
        conv.unread_count = 0
        session.add(conv)


async def _last_messages(
    session: AsyncSession, *, org_id: str, conversation_ids: list[str]
) -> dict[str, InboxMessage]:
    if not conversation_ids:
        return {}
    rows = (
        await session.execute(
            select(InboxMessage)
            .where(
                InboxMessage.organization_id == org_id,
                InboxMessage.conversation_id.in_(conversation_ids),
            )
            .order_by(InboxMessage.created_at.desc())
        )
    ).scalars().all()
    out: dict[str, InboxMessage] = {}
    for msg in rows:
        if msg.conversation_id not in out:
            out[msg.conversation_id] = msg
    return out


async def list_conversations(
    session: AsyncSession,
    *,
    org_id: str,
    status: str | None = None,
    channel: str | None = None,
    assigned_to: str | None = None,
    unassigned: bool = False,
    q: str | None = None,
    limit: int = 100,
) -> list[dict]:
    stmt = (
        select(InboxConversation, OrganizationMember, User)
        .outerjoin(OrganizationMember, OrganizationMember.id == InboxConversation.member_id)
        .outerjoin(User, User.id == OrganizationMember.user_id)
        .where(InboxConversation.organization_id == org_id)
    )
    if status:
        stmt = stmt.where(InboxConversation.status == _enum(ConversationStatus, status, ConversationStatus.OPEN))
    else:
        stmt = stmt.where(InboxConversation.status != ConversationStatus.RESOLVED)
    if channel:
        stmt = stmt.where(InboxConversation.channel == _enum(Channel, channel, Channel.OTHER))
    if unassigned:
        stmt = stmt.where(InboxConversation.assigned_to.is_(None))
    elif assigned_to:
        stmt = stmt.where(InboxConversation.assigned_to == assigned_to)
    if q:
        pattern = f"%{q.strip().lower()}%"
        stmt = stmt.where(
            func.lower(func.coalesce(InboxConversation.contact_name, "")).like(pattern)
            | func.lower(InboxConversation.contact_handle).like(pattern)
            | func.lower(func.coalesce(User.full_name, "")).like(pattern)
            | func.lower(func.coalesce(User.email, "")).like(pattern)
        )

    rows = (
        await session.execute(
            stmt.order_by(InboxConversation.last_message_at.desc()).limit(max(1, min(limit, 200)))
        )
    ).all()

    ids = [c.id for c, _m, _u in rows]
    last = await _last_messages(session, org_id=org_id, conversation_ids=ids)
    assignees = await _assignee_names(session, [c.assigned_to for c, _m, _u in rows if c.assigned_to])

    out: list[dict] = []
    for conv, member, user in rows:
        preview = last.get(conv.id)
        out.append(_conv_out(conv, member, user, assignees.get(conv.assigned_to), preview))
    return out


async def _assignee_names(session: AsyncSession, user_ids: list[str]) -> dict[str, str]:
    ids = [u for u in user_ids if u]
    if not ids:
        return {}
    rows = (
        await session.execute(select(User.id, User.full_name, User.email).where(User.id.in_(ids)))
    ).all()
    return {uid: (name or email) for uid, name, email in rows}


def _conv_out(conv, member, user, assignee_name, preview) -> dict:
    member_name = None
    if member is not None:
        member_name = member.display_name or (user.full_name if user else None) or (user.email if user else None)
    return {
        "id": conv.id,
        "channel": _value(conv.channel),
        "contact_handle": conv.contact_handle,
        "contact_name": conv.contact_name,
        "member_id": conv.member_id,
        "member_name": member_name,
        "subject": conv.subject,
        "status": _value(conv.status),
        "assigned_to": conv.assigned_to,
        "assigned_name": assignee_name,
        "last_message_at": conv.last_message_at,
        "unread_count": conv.unread_count,
        "preview": (preview.body[:140] if preview else None),
        "preview_direction": _value(preview.direction) if preview else None,
    }


def _msg_out(m: InboxMessage) -> dict:
    return {
        "id": m.id,
        "direction": _value(m.direction),
        "sender_kind": _value(m.sender_kind),
        "sender_user_id": m.sender_user_id,
        "body": m.body,
        "channel": _value(m.channel),
        "delivery_status": m.delivery_status,
        "created_at": m.created_at,
    }


async def _thread_out(session: AsyncSession, conversation_id: str) -> dict:
    conv = await session.get(InboxConversation, conversation_id)
    member = await session.get(OrganizationMember, conv.member_id) if conv and conv.member_id else None
    user = await session.get(User, member.user_id) if member else None
    assignees = await _assignee_names(session, [conv.assigned_to] if conv.assigned_to else [])
    messages = (
        await session.execute(
            select(InboxMessage)
            .where(InboxMessage.conversation_id == conversation_id)
            .order_by(InboxMessage.created_at)
        )
    ).scalars().all()
    data = _conv_out(conv, member, user, assignees.get(conv.assigned_to), None)
    data["messages"] = [_msg_out(m) for m in messages]
    return data


async def get_thread(
    session: AsyncSession, *, org_id: str, conversation_id: str
) -> dict:
    await _get_conversation(session, org_id, conversation_id)
    data = await _thread_out(session, conversation_id)
    await mark_read(session, org_id=org_id, conversation_id=conversation_id)
    return data


async def inbox_stats(session: AsyncSession, *, org_id: str, user_id: str) -> dict:
    active = InboxConversation.status != ConversationStatus.RESOLVED
    counts = (
        await session.execute(
            select(
                func.coalesce(func.sum(case((active, 1), else_=0)), 0),
                func.coalesce(
                    func.sum(
                        case(
                            (and_(active, InboxConversation.assigned_to.is_(None)), 1),
                            else_=0,
                        )
                    ),
                    0,
                ),
                func.coalesce(
                    func.sum(
                        case(
                            (and_(active, InboxConversation.assigned_to == user_id), 1),
                            else_=0,
                        )
                    ),
                    0,
                ),
                func.coalesce(
                    func.sum(
                        case((InboxConversation.status == ConversationStatus.RESOLVED, 1), else_=0)
                    ),
                    0,
                ),
                func.coalesce(
                    func.sum(case((active, InboxConversation.unread_count), else_=0)),
                    0,
                ),
            ).where(InboxConversation.organization_id == org_id)
        )
    ).one()
    return {
        "open": int(counts[0] or 0),
        "unassigned": int(counts[1] or 0),
        "mine": int(counts[2] or 0),
        "resolved": int(counts[3] or 0),
        "unread": int(counts[4] or 0),
    }


async def draft_reply(
    session: AsyncSession, *, org_id: str, conversation_id: str
) -> str:
    """Draft a reply to the thread's last inbound message with the LLM."""

    from langchain_core.messages import HumanMessage, SystemMessage

    from app.agent.model import build_chat_model

    conv = await _get_conversation(session, org_id, conversation_id)
    recent = (
        await session.execute(
            select(InboxMessage)
            .where(InboxMessage.conversation_id == conv.id)
            .order_by(InboxMessage.created_at.desc())
            .limit(6)
        )
    ).scalars().all()
    recent = list(reversed(recent))

    member = await session.get(OrganizationMember, conv.member_id) if conv.member_id else None
    who = conv.contact_name or (member.display_name if member else None) or conv.contact_handle
    channel = _value(conv.channel)

    history = "\n".join(
        f"{'Customer' if _value(m.direction) == 'inbound' else 'Gym'}: {m.body}" for m in recent
    ) or "(no messages yet)"

    system = (
        "You are the front desk of a gym, drafting a reply on a member messaging "
        f"thread ({channel}). Be warm, concise (2-3 sentences), and helpful. "
        "Return only the reply text, no greeting labels or preamble."
    )
    human = f"Contact: {who}\n\nConversation so far:\n{history}\n\nDraft the next reply."
    model = build_chat_model()
    resp = await model.ainvoke([SystemMessage(content=system), HumanMessage(content=human)])
    text = resp.content if isinstance(resp.content, str) else str(resp.content)
    return text.strip()
