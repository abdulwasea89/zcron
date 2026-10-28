import json

import pytest

from app.realtime.manager import ConnectionManager


@pytest.mark.asyncio
async def test_broadcast_publishes_tenant_and_recipient_scope():
    class Redis:
        def __init__(self):
            self.messages = []

        async def publish(self, channel, message):
            self.messages.append((channel, json.loads(message)))

    manager = ConnectionManager()
    redis = Redis()
    manager._redis = redis

    await manager.broadcast("org-a", {"type": "plan.changed"})
    await manager.broadcast_user("org-b", "user-1", {"type": "notification.created"})

    assert redis.messages[0][1]["organization_id"] == "org-a"
    assert redis.messages[0][1]["user_id"] is None
    assert redis.messages[0][1]["event"] == {"type": "plan.changed"}
    assert redis.messages[1][1]["organization_id"] == "org-b"
    assert redis.messages[1][1]["user_id"] == "user-1"
