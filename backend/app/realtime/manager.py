"""Per-organization WebSocket connection manager (Section 16 Real-Time Sync).

An owner edits a plan on the web and it appears on their phone in under ~2s: the
mutation calls ``manager.broadcast(org_id, event)`` and every socket scoped to
that org receives the JSON event. Connections are grouped by ``organization_id``
so an event for one tenant never reaches another (tenant isolation extends to the
realtime layer, Security Rule #1).

Redis pub/sub fans events out to sockets on other API workers. Delivery remains
best-effort so a realtime outage never rolls back the business mutation.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from uuid import uuid4

from fastapi import WebSocket
import redis.asyncio as aioredis

from app.core.config import settings


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
        self._redis = None
        self._source = uuid4().hex
        self._channel = f"acron:realtime:{settings.app_env}"
        self._listener: asyncio.Task | None = None

    async def start(self) -> None:
        if self._redis is None:
            self._redis = aioredis.from_url(settings.redis_url, decode_responses=True)
        if self._listener is None:
            self._listener = asyncio.create_task(self._listen())

    async def stop(self) -> None:
        if self._listener is not None:
            self._listener.cancel()
            await asyncio.gather(self._listener, return_exceptions=True)
            self._listener = None
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None

    async def _listen(self) -> None:
        while True:
            try:
                if self._redis is None:
                    return
                async with self._redis.pubsub() as pubsub:
                    await pubsub.subscribe(self._channel)
                    async for message in pubsub.listen():
                        if message.get("type") != "message":
                            continue
                        payload = json.loads(message["data"])
                        if payload.get("source") == self._source:
                            continue
                        org_id = payload["organization_id"]
                        user_id = payload.get("user_id")
                        if user_id:
                            await self.broadcast_user(org_id, user_id, payload["event"], publish=False)
                        else:
                            await self.broadcast(org_id, payload["event"], publish=False)
            except asyncio.CancelledError:
                raise
            except Exception:
                logging.warning("Realtime Redis subscription disconnected; retrying")
                await asyncio.sleep(1)

    async def _publish(self, org_id: str, event: dict, user_id: str | None = None) -> None:
        try:
            if self._redis is None:
                self._redis = aioredis.from_url(settings.redis_url, decode_responses=True)
            await asyncio.wait_for(self._redis.publish(self._channel, json.dumps({
                "source": self._source, "organization_id": org_id,
                "user_id": user_id, "event": event,
            })), timeout=1)
        except Exception:
            logging.warning("Realtime Redis publish failed; local delivery only")

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

    async def broadcast(self, org_id: str, event: dict, *, publish: bool = True) -> None:
        """Send ``event`` to every socket in ``org_id``. Best-effort.

        Dead sockets are pruned. Never raises into the caller (a failed push
        must not roll back the business mutation that triggered it).
        """

        if publish:
            await self._publish(org_id, event)
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

    async def broadcast_user(
        self, org_id: str, user_id: str, event: dict, *, publish: bool = True
    ) -> None:
        """Send ``event`` only to ``user_id``'s sockets in ``org_id``. Best-effort."""

        if publish:
            await self._publish(org_id, event, user_id)
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
