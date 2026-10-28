"""Authenticated WebSocket endpoint for tenant-scoped realtime events."""

from __future__ import annotations

import asyncio
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import and_
from sqlmodel import select

from app.core.constants import MemberStatus
from app.core.security import WEBSOCKET, now_utc, safe_decode
from app.db.rls import set_rls_context
from app.db.session import async_session_maker
from app.models.membership import OrganizationMember
from app.models.organization import Organization
from app.models.session import AuthSession
from app.models.user import User
from app.realtime import manager

router = APIRouter()


async def _authorize(token: str) -> tuple[str, str, str] | None:
    """Return the authorized org, user, and revocable session IDs."""

    payload = safe_decode(token)
    if not payload or payload.get("type") != WEBSOCKET:
        return None
    user_id = payload.get("sub")
    org_id = payload.get("org_id")
    session_id = payload.get("session_id")
    if not user_id or not org_id or not session_id:
        return None
    async with async_session_maker() as session:
        await set_rls_context(session, organization_id=org_id, user_id=user_id)
        membership = (
            await session.execute(
                select(OrganizationMember).where(
                    OrganizationMember.user_id == user_id,
                    OrganizationMember.organization_id == org_id,
                )
            )
        ).scalar_one_or_none()
        auth_session = await session.get(AuthSession, session_id)
        user = await session.get(User, user_id)
        org = await session.get(Organization, org_id)
    if (
        membership is None
        or membership.banned
        or membership.member_status == MemberStatus.BANNED
        or user is None
        or not user.is_active
        or org is None
        or (org.mfa_required and not user.mfa_enabled)
        or auth_session is None
        or auth_session.user_id != user_id
        or auth_session.organization_id != org_id
        or auth_session.revoked
        or (auth_session.expires_at is not None and auth_session.expires_at < now_utc())
    ):
        return None
    return org_id, user_id, session_id


async def _session_is_active(session_id: str, user_id: str, org_id: str) -> bool:
    async with async_session_maker() as session:
        await set_rls_context(session, organization_id=org_id, user_id=user_id)
        active = await session.execute(
            select(AuthSession.id)
            .join(User, User.id == AuthSession.user_id)
            .join(
                OrganizationMember,
                and_(
                    OrganizationMember.user_id == User.id,
                    OrganizationMember.organization_id == org_id,
                ),
            )
            .join(Organization, Organization.id == org_id)
            .where(
                AuthSession.id == session_id,
                AuthSession.user_id == user_id,
                AuthSession.organization_id == org_id,
                AuthSession.revoked.is_(False),
                User.is_active.is_(True),
                OrganizationMember.banned.is_(False),
                OrganizationMember.member_status != MemberStatus.BANNED,
                (Organization.mfa_required.is_(False) | User.mfa_enabled.is_(True)),
                (AuthSession.expires_at.is_(None) | (AuthSession.expires_at >= now_utc())),
            )
        )
        return active.scalar_one_or_none() is not None


@router.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        token = await asyncio.wait_for(websocket.receive_text(), timeout=5)
    except asyncio.TimeoutError:
        await websocket.close(code=1008)
        return
    except WebSocketDisconnect:
        return
    if len(token) > 4096:
        await websocket.close(code=1008)
        return
    authorized = await _authorize(token)
    if authorized is None:
        # 1008 = policy violation (auth failure).
        await websocket.close(code=1008)
        return
    org_id, user_id, session_id = authorized

    await manager.connect(org_id, user_id, websocket)
    try:
        await websocket.send_json({"type": "connected", "organization_id": org_id})
        last_session_check = time.monotonic()
        while True:
            try:
                msg = await asyncio.wait_for(websocket.receive_text(), timeout=25)
            except asyncio.TimeoutError:
                msg = ""
            if time.monotonic() - last_session_check >= 25:
                if not await _session_is_active(session_id, user_id, org_id):
                    await websocket.close(code=1008)
                    break
                last_session_check = time.monotonic()
            if msg == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(org_id, websocket, user_id=user_id)
