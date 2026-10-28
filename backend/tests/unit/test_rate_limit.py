from fastapi import HTTPException
import pytest

from app.core.config import settings
from app.core.rate_limit import RateLimiter, _MemoryWindow


def test_memory_fallback_bounds_distinct_keys():
    memory = _MemoryWindow()
    for index in range(10_001):
        memory.hit(str(index), 1, 60)
    assert len(memory._events) == 10_000
    assert "0" not in memory._events


@pytest.mark.parametrize("app_env", ["production", "prod"])
async def test_redis_failure_fails_closed_in_production(monkeypatch, app_env):
    limiter = RateLimiter()
    limiter._redis = None
    monkeypatch.setattr(settings, "app_env", app_env)
    with pytest.raises(HTTPException) as exc:
        await limiter.hit("login", 5, 60)
    assert exc.value.status_code == 503


async def test_redis_failure_uses_memory_in_development(monkeypatch):
    limiter = RateLimiter()
    limiter._redis = None
    monkeypatch.setattr(settings, "app_env", "development")
    assert await limiter.hit("login", 1, 60) == (True, 0)
    assert await limiter.hit("login", 1, 60) == (False, 0)
