import hashlib
from unittest.mock import AsyncMock

import pytest

from app.integrations import hibp


@pytest.mark.parametrize("compromised", [True, False])
async def test_breach_check_uses_only_hash_prefix(monkeypatch, compromised):
    password = "test-only-password"
    digest = hashlib.sha1(password.encode()).hexdigest().upper()
    response = type("Response", (), {
        "text": f"{digest[5:]}:42" if compromised else "OTHER:1",
        "raise_for_status": lambda self: None,
    })()
    request_get = AsyncMock(return_value=response)

    class Client:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            pass

        async def get(self, *args, **kwargs):
            return await request_get(*args, **kwargs)

    monkeypatch.setattr(hibp.settings, "hibp_enabled", True)
    monkeypatch.setattr(hibp.httpx, "AsyncClient", Client)
    assert await hibp.password_is_pwned(password) is compromised
    url = request_get.await_args.args[0]
    assert url.endswith(f"/range/{digest[:5]}")
    assert password not in url and digest[5:] not in url
