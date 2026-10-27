import pytest

from app.integrations import email


@pytest.mark.asyncio
async def test_resend_campaign_sender_returns_provider_message_id(monkeypatch):
    async def run_inline(function, *args, **kwargs):
        return function(*args, **kwargs)

    monkeypatch.setattr(email.settings, "smtp_host", "")
    monkeypatch.setattr(email.settings, "smtp_user", "")
    monkeypatch.setattr(email.settings, "smtp_password", "")
    monkeypatch.setattr(email.settings, "resend_api_key", "re_test")
    monkeypatch.setattr(email, "_send_sync", lambda _params: {"id": "email-123"})
    monkeypatch.setattr(email.asyncio, "to_thread", run_inline)

    result = await email.send_email_tracked_safe("member@example.com", "Gym update", "Hello")

    assert result.accepted is True
    assert result.provider_message_id == "email-123"
