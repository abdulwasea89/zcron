"""Per-organization WebSocket connection manager (Section 16 Real-Time Sync).

An owner edits a plan on the web and it appears on their phone in under ~2s: the
mutation calls ``manager.broadcast(org_id, event)`` and every socket scoped to
that org receives the JSON event. Connections are grouped by ``organization_id``
so an event for one tenant never reaches another (tenant isolation extends to the
realtime layer, Security Rule #1).

The manager holds no DB state and is a process-local singleton. In a multi-worker
deployment a Redis pub/sub fan-out would sit behind ``broadcast``; the call sites
do not change. ``broadcast`` is best-effort: a send failure just drops that dead
socket, it never breaks the request doing the mutation.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict

from fastapi import WebSocket




class ConnectionManager:
    """Tracks live WebSocket connections keyed by org and user.

    Org keying broadcasts tenant-wide events (plan.changed, gym status, …).
    User keying lets per-recipient events like a notification reach exactly one
    member of the org — the recipient's other sockets (web + mobile) and nobody
    else's.
    """

    def __init__(self) -> None:
        self._by_org: dict[str, set[WebSocket]] = defaultdict(set)
        self._by_user: dict[str, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect(self, org_id: str, user_id: str, websocket: WebSocket) -> None:
        """Register an already accepted socket under its org and user."""

        async with self._lock:
            self._by_org[org_id].add(websocket)
            self._by_user[user_id].add(websocket)

    async def disconnect(self, org_id: str, websocket: WebSocket, user_id: str | None = None) -> None:
        async with self._lock:
            conns = self._by_org.get(org_id)
            if conns is not None:
                conns.discard(websocket)
                if not conns:
                    self._by_org.pop(org_id, None)
            if user_id is not None:
                uconns = self._by_user.get(user_id)
                if uconns is not None:
                    uconns.discard(websocket)
                    if not uconns:
                        self._by_user.pop(user_id, None)

    def connection_count(self, org_id: str) -> int:
        return len(self._by_org.get(org_id, ()))

    async def broadcast(self, org_id: str, event: dict) -> None:
        """Send ``event`` to every socket in ``org_id``. Best-effort.

        Dead sockets are pruned. Never raises into the caller (a failed push
        must not roll back the business mutation that triggered it).
        """

        targets = list(self._by_org.get(org_id, ()))
        if not targets:
            return
        dead = await self._send_all(targets, event)
        if dead:
            async with self._lock:
                conns = self._by_org.get(org_id)
                if conns is not None:
                    for ws in dead:
                        conns.discard(ws)
                    if not conns:
                        self._by_org.pop(org_id, None)

    async def broadcast_user(self, org_id: str, user_id: str, event: dict) -> None:
        """Send ``event`` only to ``user_id``'s sockets in ``org_id``. Best-effort."""

        targets = [ws for ws in self._by_user.get(user_id, ()) if ws in self._by_org.get(org_id, ())]
        if not targets:
            return
        dead = await self._send_all(targets, event)
        if dead:
            async with self._lock:
                uconns = self._by_user.get(user_id)
                oconns = self._by_org.get(org_id)
                for ws in dead:
                    if uconns is not None:
                        uconns.discard(ws)
                    if oconns is not None:
                        oconns.discard(ws)
                if uconns is not None and not uconns:
                    self._by_user.pop(user_id, None)
                if oconns is not None and not oconns:
                    self._by_org.pop(org_id, None)

    @staticmethod
    async def _send_all(targets: list[WebSocket], event: dict) -> list[WebSocket]:
        """Push ``event`` to every socket; return the ones that failed."""

        dead: list[WebSocket] = []
        for ws in targets:
            try:
                await ws.send_json(event)
            except Exception:
                dead.append(ws)
        return dead


# Process-local singleton used by routes/services to publish events.
manager = ConnectionManager()
