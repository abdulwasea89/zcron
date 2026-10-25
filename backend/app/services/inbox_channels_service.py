"""Secure per-workspace inbox provider connections."""

from __future__ import annotations

import json
import secrets
import smtplib
from email.utils import parseaddr
from typing import Any

import httpx
from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.config import settings
from app.core.security import now_utc
from app.models.inbox_channel import InboxChannelConnection

CHANNELS = {"email", "sms", "whatsapp", "telegram", "line", "instagram", "messenger", "wechat", "web_chat"}


def _fernet() -> Fernet:
    if not settings.inbox_encryption_key:
        raise HTTPException(
            status_code=503,
            detail="Inbox credential encryption is not configured. Set INBOX_ENCRYPTION_KEY in the backend environment.",
        )
    try:
        return Fernet(settings.inbox_encryption_key.encode())
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=503, detail="INBOX_ENCRYPTION_KEY is invalid.") from exc


def encrypt_credentials(credentials: dict[str, Any]) -> str:
    return _fernet().encrypt(json.dumps(credentials, separators=(",", ":")).encode()).decode()


def decrypt_credentials(connection: InboxChannelConnection) -> dict[str, Any]:
    try:
        raw = _fernet().decrypt(connection.credentials_ciphertext.encode())
        value = json.loads(raw)
    except (InvalidToken, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=500, detail="Saved inbox credentials cannot be decrypted.") from exc
    if not isinstance(value, dict):
        raise HTTPException(status_code=500, detail="Saved inbox credentials are invalid.")
    return value


async def _verify_email(credentials: dict[str, Any]) -> None:
    if credentials.get("host"):
        def verify_smtp() -> None:
            with smtplib.SMTP(credentials["host"], int(credentials["port"]), timeout=12) as server:
                if credentials.get("use_tls", True):
                    server.starttls()
                server.login(credentials["username"], credentials["password"])
                server.noop()

        import asyncio

        try:
            await asyncio.to_thread(verify_smtp)
        except Exception as exc:
            raise HTTPException(status_code=422, detail="Could not authenticate with this SMTP server.") from exc
    if credentials.get("resend_api_key"):
        try:
            async with httpx.AsyncClient(timeout=12) as client:
                response = await client.get("https://api.resend.com/domains", headers={"Authorization": f"Bearer {credentials['resend_api_key']}"})
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=422, detail="Resend could not verify this API key.") from exc


async def _verify_twilio(credentials: dict[str, Any]) -> None:
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            response = await client.get(
                f"https://api.twilio.com/2010-04-01/Accounts/{credentials['account_sid']}.json",
                auth=(credentials["account_sid"], credentials["auth_token"]),
            )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=422, detail="Twilio could not verify these account credentials.") from exc


async def _telegram_request(token: str, method: str, payload: dict | None = None) -> dict:
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            response = await client.post(
                f"https://api.telegram.org/bot{token}/{method}", json=payload or {}
            )
        response.raise_for_status()
        result = response.json()
        if not result.get("ok"):
            raise ValueError("Telegram returned an unsuccessful response")
        return result
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="Telegram could not verify or configure this bot.") from exc


async def _verify_line(credentials: dict[str, Any]) -> None:
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            response = await client.get(
                "https://api.line.me/v2/bot/info",
                headers={"Authorization": f"Bearer {credentials['access_token']}"},
            )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=422, detail="LINE could not verify this channel access token.") from exc


async def _verify_meta(credentials: dict[str, Any]) -> None:
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            response = await client.get(
                f"https://graph.facebook.com/{settings.inbox_meta_graph_version}/{credentials['sender_id']}",
                params={"fields": "id", "access_token": credentials["page_access_token"]},
            )
        response.raise_for_status()
        if str(response.json().get("id")) != credentials["sender_id"]:
            raise ValueError("Meta sender id mismatch")
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="Meta could not verify this page or Instagram access token.") from exc


async def _verify_wechat(credentials: dict[str, Any]) -> None:
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            response = await client.get(
                "https://api.weixin.qq.com/cgi-bin/token",
                params={"grant_type": "client_credential", "appid": credentials["app_id"], "secret": credentials["app_secret"]},
            )
        response.raise_for_status()
        if not response.json().get("access_token"):
            raise ValueError("WeChat did not return an access token")
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="WeChat could not verify this Official Account.") from exc


def _validate(channel: str, source: dict[str, Any]) -> dict[str, Any]:
    if channel not in CHANNELS:
        raise HTTPException(status_code=404, detail="This inbox channel cannot be connected yet.")
    allowed = {
        "email": {"host", "port", "username", "password", "from_email", "use_tls", "resend_api_key", "inbound_webhook_secret"},
        "sms": {"account_sid", "auth_token", "from_number", "forward_to_number"},
        "whatsapp": {"account_sid", "auth_token", "from_number"},
        "telegram": {"bot_token"},
        "line": {"access_token", "channel_secret"},
        "instagram": {"sender_id", "page_access_token", "app_secret", "verify_token"},
        "messenger": {"sender_id", "page_access_token", "app_secret", "verify_token"},
        "wechat": {"app_id", "app_secret", "verify_token"},
        "web_chat": {"enabled"},
    }[channel]
    creds = {str(key): value for key, value in source.items() if key in allowed and value is not None}
    if channel == "email":
        creds["host"] = str(creds.get("host", "")).strip()
        creds["username"] = str(creds.get("username", "")).strip()
        creds["from_email"] = str(creds.get("from_email", "")).strip()
        creds["resend_api_key"] = str(creds.get("resend_api_key", "")).strip()
        creds["inbound_webhook_secret"] = str(creds.get("inbound_webhook_secret", "")).strip()
        smtp_ready = all(creds.get(key) for key in ("host", "port", "username", "password"))
        if not (smtp_ready or creds["resend_api_key"]) or not creds["from_email"]:
            raise HTTPException(status_code=422, detail="Provide complete SMTP credentials or a Resend API key, plus a sender email.")
        if not smtp_ready:
            for key in ("host", "port", "username", "password"):
                creds.pop(key, None)
        if "@" not in parseaddr(creds["from_email"])[1]:
            raise HTTPException(status_code=422, detail="Enter a valid sender email address.")
        if smtp_ready:
            try:
                creds["port"] = int(creds["port"])
            except (ValueError, TypeError) as exc:
                raise HTTPException(status_code=422, detail="SMTP port must be a number.") from exc
        tls = creds.get("use_tls", True)
        creds["use_tls"] = tls if isinstance(tls, bool) else str(tls).lower() not in {"0", "false", "off", "no"}
    elif channel in ("sms", "whatsapp"):
        required = ("account_sid", "auth_token", "from_number")
        for key in required:
            creds[key] = str(creds.get(key, "")).strip()
        if not all(creds[key] for key in required):
            raise HTTPException(status_code=422, detail="Enter the Twilio Account SID, Auth Token, and sender number.")
        if channel == "whatsapp" and not creds["from_number"].startswith("whatsapp:"):
            creds["from_number"] = f"whatsapp:{creds['from_number']}"
        if channel == "sms":
            forward_to = str(creds.get("forward_to_number", "")).strip()
            if forward_to and (not forward_to.startswith("+") or not forward_to[1:].isdigit() or not 7 <= len(forward_to[1:]) <= 15):
                raise HTTPException(status_code=422, detail="Enter the gym call-forward number in international format, such as +14155550123.")
            if forward_to:
                creds["forward_to_number"] = forward_to
            else:
                creds.pop("forward_to_number", None)
    elif channel == "telegram":
        creds["bot_token"] = str(creds.get("bot_token", "")).strip()
        if not creds["bot_token"]:
            raise HTTPException(status_code=422, detail="Enter the Telegram bot token.")
    elif channel == "line":
        for key in ("access_token", "channel_secret"):
            creds[key] = str(creds.get(key, "")).strip()
        if not creds["access_token"] or not creds["channel_secret"]:
            raise HTTPException(status_code=422, detail="Enter the LINE channel access token and channel secret.")
    elif channel in ("instagram", "messenger"):
        for key in ("sender_id", "page_access_token", "app_secret", "verify_token"):
            creds[key] = str(creds.get(key, "")).strip()
        if not all(creds.values()):
            raise HTTPException(status_code=422, detail="Enter the account ID, page access token, app secret, and webhook verify token.")
    elif channel == "wechat":
        for key in ("app_id", "app_secret", "verify_token"):
            creds[key] = str(creds.get(key, "")).strip()
        if not all(creds.values()):
            raise HTTPException(status_code=422, detail="Enter the WeChat App ID, App Secret, and webhook token.")
    elif channel == "web_chat":
        if source.get("enabled") is not True:
            raise HTTPException(status_code=422, detail="Enable the member web chat before connecting it.")
        creds = {"enabled": True}
    return creds


async def _connection(session: AsyncSession, org_id: str, channel: str):
    return (
        await session.execute(
            select(InboxChannelConnection).where(
                InboxChannelConnection.organization_id == org_id,
                InboxChannelConnection.channel == channel,
            )
        )
    ).scalar_one_or_none()


def webhook_url(org_id: str, channel: str, token: str | None = None) -> str | None:
    if channel == "web_chat":
        return None
    if channel == "email":
        return f"{settings.inbox_public_webhook_base_url.rstrip('/')}/api/v1/inbox/webhooks/{org_id}/resend" if settings.inbox_public_webhook_base_url else None
    if not settings.inbox_public_webhook_base_url:
        return None
    suffix = "twilio" if channel in ("sms", "whatsapp") else "meta" if channel in ("instagram", "messenger") else channel
    url = f"{settings.inbox_public_webhook_base_url.rstrip('/')}/api/v1/inbox/webhooks/{org_id}/{suffix}"
    if channel in {"instagram", "messenger"}:
        url = f"{url}/{channel}"
    return f"{url}?hook={token}" if token and channel in {"line", "instagram", "messenger", "wechat"} else url


async def list_connections(session: AsyncSession, org_id: str) -> list[dict]:
    rows = (
        await session.execute(
            select(InboxChannelConnection).where(InboxChannelConnection.organization_id == org_id)
        )
    ).scalars().all()
    by_channel = {row.channel: row for row in rows}
    from app.models.organization import Organization
    org = await session.get(Organization, org_id)
    return [
        {
            "channel": channel,
            "connected": channel in by_channel,
            "connected_at": by_channel[channel].connected_at if channel in by_channel else None,
            "webhook_url": (
                f"{settings.frontend_url.rstrip('/')}/chat/{org.org_code}"
                if channel == "web_chat" and channel in by_channel and org
                else webhook_url(org_id, channel, by_channel[channel].webhook_token if channel in by_channel else None)
                if channel != "email" or (channel in by_channel and decrypt_credentials(by_channel[channel]).get("inbound_webhook_secret"))
                else None
            ),
            "voice_webhook_url": (
                f"{settings.inbox_public_webhook_base_url.rstrip('/')}/api/v1/inbox/webhooks/{org_id}/twilio/voice"
                if channel == "sms" and channel in by_channel and decrypt_credentials(by_channel[channel]).get("forward_to_number")
                and settings.inbox_public_webhook_base_url else None
            ),
        }
        for channel in sorted(CHANNELS)
    ]


async def connect(
    session: AsyncSession, *, org_id: str, channel: str, source: dict[str, Any]
) -> dict:
    creds = _validate(channel, source)
    if (channel in {"sms", "whatsapp", "telegram", "line", "instagram", "messenger", "wechat"} or (channel == "email" and creds.get("inbound_webhook_secret"))) and not settings.inbox_public_webhook_base_url.startswith("https://"):
        raise HTTPException(
            status_code=422,
            detail="Set INBOX_PUBLIC_WEBHOOK_BASE_URL to your public HTTPS API origin before connecting inbound messaging channels.",
        )
    if channel == "email":
        await _verify_email(creds)
    elif channel in ("sms", "whatsapp"):
        await _verify_twilio(creds)
    elif channel == "line":
        await _verify_line(creds)
    elif channel in ("instagram", "messenger"):
        await _verify_meta(creds)
    elif channel == "wechat":
        await _verify_wechat(creds)

    hook_token = secrets.token_urlsafe(32) if channel in {"line", "instagram", "messenger", "wechat"} else None
    url = webhook_url(org_id, channel, hook_token)
    if channel == "email" and not creds.get("inbound_webhook_secret"):
        url = None
    if channel == "web_chat":
        from app.models.organization import Organization
        org = await session.get(Organization, org_id)
        url = f"{settings.frontend_url.rstrip('/')}/chat/{org.org_code}" if org else None
    if channel == "telegram":
        creds["webhook_secret"] = secrets.token_urlsafe(32).replace(".", "_")
        await _telegram_request(
            creds["bot_token"], "setWebhook",
            {"url": url, "secret_token": creds["webhook_secret"], "allowed_updates": ["message"]},
        )

    cipher = encrypt_credentials(creds)
    row = await _connection(session, org_id, channel)
    if row is None:
        row = InboxChannelConnection(
            organization_id=org_id, channel=channel, credentials_ciphertext=cipher,
            webhook_token=hook_token,
        )
    else:
        row.credentials_ciphertext = cipher
        row.webhook_token = hook_token
        row.connected_at = now_utc()
    session.add(row)
    await session.flush()
    voice_url = (
        f"{settings.inbox_public_webhook_base_url.rstrip('/')}/api/v1/inbox/webhooks/{org_id}/twilio/voice"
        if channel == "sms" and creds.get("forward_to_number") and settings.inbox_public_webhook_base_url else None
    )
    return {
        "channel": channel, "connected": True, "connected_at": row.connected_at,
        "webhook_url": url, "voice_webhook_url": voice_url,
    }


async def disconnect(session: AsyncSession, *, org_id: str, channel: str) -> None:
    if channel not in CHANNELS:
        raise HTTPException(status_code=404, detail="This inbox channel cannot be disconnected here.")
    row = await _connection(session, org_id, channel)
    if row is None:
        return
    if channel == "telegram":
        creds = decrypt_credentials(row)
        try:
            await _telegram_request(creds["bot_token"], "deleteWebhook")
        except HTTPException:
            # Allow owners to remove stale/revoked bot credentials even if the
            # provider no longer accepts an API request with the saved token.
            pass
    await session.delete(row)


async def get_credentials(session: AsyncSession, org_id: str, channel: str) -> dict | None:
    row = await _connection(session, org_id, channel)
    return decrypt_credentials(row) if row else None


async def get_connection(session: AsyncSession, org_id: str, channel: str):
    return await _connection(session, org_id, channel)
