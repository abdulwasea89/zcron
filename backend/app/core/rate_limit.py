"""Sliding-window rate limiting with Redis, degrading to in-process memory.

Used for signup protection (Section 7.2), email-verification resends
(Section 4.3), and failed-login backoff (Section 5.7). When Redis is
unreachable, an in-memory fallback keeps the API functional in local dev.
"""

from __future__ import annotations

import time
from collections import OrderedDict
from uuid import uuid4

from fastapi import HTTPException

try:  # redis is optional in local dev
    import redis.asyncio as aioredis
except Exception:  # pragma: no cover
    aioredis = None  # type: ignore

from app.core.config import settings


class _MemoryWindow:
    """Bounded process-local fallback for development only."""

    def __init__(self) -> None:
        self._events: OrderedDict[str, list[float]] = OrderedDict()

    def hit(self, key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
        now = time.time()
        cutoff = now - window_seconds
        events = [t for t in self._events.get(key, []) if t >= cutoff]
        self._events.pop(key, None)
        if not events and len(self._events) >= 10_000:
            self._events.popitem(last=False)
        allowed = len(events) < limit
        if allowed:
            events.append(now)
        self._events[key] = events
        self._events.move_to_end(key)
        remaining = max(0, limit - len(events))
        return allowed, remaining


class RateLimiter:
    def __init__(self) -> None:
        self._memory = _MemoryWindow()
        self._redis = None
        if aioredis is not None:
            try:
                self._redis = aioredis.from_url(settings.redis_url, decode_responses=True)
            except Exception:
                # No Redis reachable at startup; fall through to the in-process
                # window so rate limiting still applies rather than 500-ing.
                self._redis = None

    async def hit(self, key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
        """Record an event. Returns (allowed, remaining)."""

        if self._redis is not None:
            try:
                return await self._redis_hit(key, limit, window_seconds)
            except Exception:
                if settings.app_env.strip().lower() in {"prod", "production"}:
                    raise HTTPException(503, "Rate limiting is temporarily unavailable.")
        elif settings.app_env.strip().lower() in {"prod", "production"}:
            raise HTTPException(503, "Rate limiting is temporarily unavailable.")
        return self._memory.hit(key, limit, window_seconds)

    async def _redis_hit(self, key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
        now = time.time()
        cutoff = now - window_seconds
        member = f"{now:.6f}:{uuid4().hex}"
        pipe = self._redis.pipeline()
        pipe.zremrangebyscore(key, 0, cutoff)
        pipe.zadd(key, {member: now})
        pipe.zcard(key)
        pipe.expire(key, window_seconds)
        _, _, count, _ = await pipe.execute()
        allowed = count <= limit
        if not allowed:
            await self._redis.zrem(key, member)
            count -= 1
        return allowed, max(0, limit - count)


rate_limiter = RateLimiter()
