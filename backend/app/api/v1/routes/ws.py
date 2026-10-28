"""WebSocket endpoint for real-time sync (Section 16).

Clients connect to ``/api/v1/ws?token=<access_jwt>`` (browsers can't set an
Authorization header on a WebSocket, so the access token is passed as a query
param). The token is validated exactly like the HTTP path: it must be an access
token carrying an ``org_id`` and the membership must still exist and be unbanned.
The socket is then registered under that org and receives every event broadcast
to the tenant. Inbound messages are ignored except ``ping`` (-> ``pong``), which
keeps proxies from idling the connection.
"""

from __future__ import annotations

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from sqlmodel import select

from app.core.security import ACCESS, safe_decode
from app.db.session import async_session_maker
from app.models.membership import OrganizationMember
from app.models.organization import Organization
from app.models.user import User
from app.realtime import manager

router = APIRouter()


async def _authorize(token: str) -> tuple[str, str] | None:
    """Return (org_id, user_id) the token is scoped to, or None if unauthorized."""

    payload = safe_decode(token)
    if not payload or payload.get("type") != ACCESS:
        return None
    user_id = payload.get("sub")
    org_id = payload.get("org_id")
    if not user_id or not org_id:
        return None
    async with async_session_maker() as session:
        membership = (
            await session.execute(
                select(OrganizationMember).where(
                    OrganizationMember.user_id == user_id,
                    OrganizationMember.organization_id == org_id,
                )
            )
        ).scalar_one_or_none()
        user = await session.get(User, user_id)
        org = await session.get(Organization, org_id)
    if (
        membership is None
        or membership.banned
        or user is None
        or not user.is_active
        or (org is not None and org.mfa_required and not user.mfa_enabled)
    ):
        return None
    return org_id, user_id


@router.websocket("/ws")
async def ws_endpoint(websocket: WebSocket, token: str = Query(default="")):
    authorized = await _authorize(token)
    if authorized is None:
        # 1008 = policy violation (auth failure).
        await websocket.close(code=1008)
        return
    org_id, user_id = authorized

    await manager.connect(org_id, user_id, websocket)
    try:
        await websocket.send_json({"type": "connected", "organization_id": org_id})
        while True:
            msg = await websocket.receive_text()
            if msg == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(org_id, websocket, user_id=user_id)
