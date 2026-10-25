"""Outbound transports for the shared staff inbox.

These adapters return a provider message id only after the provider accepts the
request. Missing credentials and unsupported channels are explicit failures;
the inbox must never label a locally stored reply as delivered.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import uuid

import httpx

from app.core.constants import Channel


class InboxDeliveryError(RuntimeError):
    """A provider is unavailable or rejected an outbound message."""


@dataclass(frozen=True)
class DeliveryReceipt:
    provider_message_id: str | None


async def deliver(channel: Channel, recipient: str, body: str, credentials: dict | None = None, *, status_callback: str | None = None, content_sid: str | None = None, content_variables: dict[str, str] | None = None) -> DeliveryReceipt:
    """Send one reply using the configured transport for ``channel``."""

    if channel == Channel.WEB_CHAT:
        # The reply is persisted in the shared thread; the public chat client
        # reads it with its signed session token.
        return DeliveryReceipt(None)

    if channel == Channel.EMAIL:
        if credentials and credentials.get("resend_api_key") and not credentials.get("host"):
            try:
                async with httpx.AsyncClient(timeout=15) as client:
                    response = await client.post(
                        "https://api.resend.com/emails",
                        headers={"Authorization": f"Bearer {credentials['resend_api_key']}", "Idempotency-Key": f"inbox-{uuid.uuid4().hex}"},
                        json={"from": credentials["from_email"], "to": [recipient], "subject": "Message from your gym", "text": body},
                    )
                response.raise_for_status()
                return DeliveryReceipt(str(response.json().get("id") or "") or None)
            except (httpx.HTTPError, KeyError, ValueError) as exc:
                raise InboxDeliveryError("Resend did not accept the email.") from exc
        from app.integrations.email import EmailDeliveryError, send_email

        try:
            smtp = credentials if credentials and credentials.get("host") else None
            if smtp is None:
                raise InboxDeliveryError("Email delivery is not connected for this workspace.")
            accepted = await send_email(recipient, "Message from your gym", body, smtp_config=smtp)
        except EmailDeliveryError as exc:
            raise InboxDeliveryError("Email provider rejected the message.") from exc
        if not accepted:
            raise InboxDeliveryError("Email delivery is not configured.")
        return DeliveryReceipt(None)

    if channel in (Channel.SMS, Channel.WHATSAPP):
        sid = (credentials or {}).get("account_sid")
        token = (credentials or {}).get("auth_token")
        sender = (
            (credentials or {}).get("from_number")
            if channel == Channel.WHATSAPP
            else (credentials or {}).get("from_number")
        )
        if not (sid and token and sender):
            raise InboxDeliveryError(f"{channel.value.title()} delivery is not configured.")
        to = recipient.strip()
        from_number = sender.strip()
        if channel == Channel.WHATSAPP:
            to = to if to.startswith("whatsapp:") else f"whatsapp:{to}"
            from_number = from_number if from_number.startswith("whatsapp:") else f"whatsapp:{from_number}"
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                data = {"To": to, "From": from_number, "Body": body}
                if channel == Channel.WHATSAPP and content_sid:
                    data.pop("Body")
                    data["ContentSid"] = content_sid
                    data["ContentVariables"] = json.dumps(content_variables or {})
                if status_callback:
                    data["StatusCallback"] = status_callback
                response = await client.post(
                    f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
                    auth=(sid, token),
                    data=data,
                )
            response.raise_for_status()
            payload = response.json()
            message_sid = payload.get("sid")
            if not isinstance(message_sid, str) or not message_sid.strip() or payload.get("status") in {"failed", "undelivered"}:
                raise InboxDeliveryError("Twilio did not accept the message.")
            return DeliveryReceipt(message_sid)
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            raise InboxDeliveryError("Twilio did not accept the message.") from exc

    if channel == Channel.TELEGRAM:
        token = (credentials or {}).get("bot_token")
        if not token:
            raise InboxDeliveryError("Telegram delivery is not configured.")
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={"chat_id": recipient, "text": body},
                )
            response.raise_for_status()
            payload = response.json()
            if not payload.get("ok"):
                raise InboxDeliveryError("Telegram did not accept the message.")
            return DeliveryReceipt(str(payload["result"]["message_id"]))
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            raise InboxDeliveryError("Telegram did not accept the message.") from exc

    if channel == Channel.LINE:
        token = (credentials or {}).get("access_token")
        if not token:
            raise InboxDeliveryError("LINE delivery is not configured.")
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.post(
                    "https://api.line.me/v2/bot/message/push",
                    headers={"Authorization": f"Bearer {token}"},
                    json={"to": recipient, "messages": [{"type": "text", "text": body}]},
                )
            response.raise_for_status()
            return DeliveryReceipt(response.headers.get("x-line-request-id"))
        except httpx.HTTPError as exc:
            raise InboxDeliveryError("LINE did not accept the message.") from exc

    if channel in (Channel.INSTAGRAM, Channel.MESSENGER):
        sender_id = (credentials or {}).get("sender_id")
        token = (credentials or {}).get("page_access_token")
        if not (sender_id and token):
            raise InboxDeliveryError(f"{channel.value.title()} is not connected for this workspace.")
        try:
            from app.core.config import settings
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.post(
                    f"https://graph.facebook.com/{settings.inbox_meta_graph_version}/{sender_id}/messages",
                    params={"access_token": token},
                    json={"recipient": {"id": recipient}, "message": {"text": body}},
                )
            response.raise_for_status()
            return DeliveryReceipt(str(response.json().get("message_id") or "") or None)
        except (httpx.HTTPError, ValueError) as exc:
            raise InboxDeliveryError(f"Meta did not accept the {channel.value} message.") from exc

    if channel == Channel.WECHAT:
        app_id = (credentials or {}).get("app_id")
        app_secret = (credentials or {}).get("app_secret")
        if not (app_id and app_secret):
            raise InboxDeliveryError("WeChat Official Account is not connected for this workspace.")
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                token_response = await client.get(
                    "https://api.weixin.qq.com/cgi-bin/token",
                    params={"grant_type": "client_credential", "appid": app_id, "secret": app_secret},
                )
                token_response.raise_for_status()
                token_data = token_response.json()
                token = token_data.get("access_token")
                if not token:
                    raise InboxDeliveryError("WeChat could not issue an access token.")
                response = await client.post(
                    "https://api.weixin.qq.com/cgi-bin/message/custom/send",
                    params={"access_token": token},
                    json={"touser": recipient, "msgtype": "text", "text": {"content": body}},
                )
            response.raise_for_status()
            data = response.json()
            if data.get("errcode", 0) != 0:
                raise InboxDeliveryError("WeChat rejected the message.")
            return DeliveryReceipt(None)
        except httpx.HTTPError as exc:
            raise InboxDeliveryError("WeChat did not accept the message.") from exc

    raise InboxDeliveryError(f"Outbound replies are not available for {channel.value}.")
