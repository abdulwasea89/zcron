"""Signed provider webhooks bound to saved workspace connections."""
from __future__ import annotations

import base64
import hashlib
from html import escape
import hmac
import json
import re
import time
import xml.etree.ElementTree as ET
from email.utils import parseaddr
from urllib.parse import parse_qsl

from fastapi import APIRouter, Depends, HTTPException, Request, Response
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.api.deps import get_session
from app.core.config import settings
from app.core.constants import CampaignDeliveryStatus, Channel
from app.models.campaign import CampaignDelivery
from app.models.organization import Organization
from app.models.inbox import InboxConversation, InboxMessage
from app.models.lead import Lead
from app.models.membership import OrganizationMember
from app.core.constants import Role
from app.realtime import events
from app.services import inbox_channels_service as channels
from app.services.inbox_service import record_inbound
from app.services import idempotency_service, leads_service

router = APIRouter()


def _public_url(request: Request) -> str:
    base = settings.inbox_public_webhook_base_url.rstrip("/")
    if not base:
        raise HTTPException(status_code=503, detail="Public inbox webhook URL is not configured.")
    return f"{base}{request.url.path}"


def _verify_twilio(request_url: str, signature: str, fields: dict[str, str], token: str) -> bool:
    if not token or not signature:
        return False
    material = request_url + "".join(key + fields[key] for key in sorted(fields))
    expected = base64.b64encode(hmac.new(token.encode(), material.encode(), hashlib.sha1).digest()).decode()
    return hmac.compare_digest(expected, signature)


async def _check_org(session: AsyncSession, org_id: str) -> None:
    if await session.get(Organization, org_id) is None:
        raise HTTPException(status_code=404, detail="Workspace not found.")


def _apply_campaign_sms_status(delivery: CampaignDelivery, status: str, error_code: str | None) -> None:
    if delivery.delivery_status in {"delivered", "failed", "undelivered"}:
        return
    if status == "delivered":
        delivery.delivery_status = "delivered"
        delivery.error = None
    elif status in {"failed", "undelivered"}:
        delivery.delivery_status = "failed"
        delivery.status = CampaignDeliveryStatus.FAILED
        delivery.error = f"Twilio delivery failed{f' ({error_code})' if error_code else ''}."
    elif status in {"sent", "queued", "accepted", "sending", "scheduled"}:
        delivery.delivery_status = status


@router.post("/webhooks/{org_id}/twilio")
async def twilio_inbound(org_id: str, request: Request, session: AsyncSession = Depends(get_session)):
    raw = (await request.body()).decode("utf-8", errors="replace")
    fields = dict(parse_qsl(raw, keep_blank_values=True))
    sender = fields.get("From", "").strip()
    channel = Channel.WHATSAPP if sender.startswith("whatsapp:") else Channel.SMS
    credentials = await channels.get_credentials(session, org_id, channel.value)
    token = (credentials or {}).get("auth_token") or ""
    signature = request.headers.get("x-twilio-signature", "")
    if not _verify_twilio(_public_url(request), signature, fields, token):
        raise HTTPException(status_code=403, detail="Invalid provider signature.")
    await _check_org(session, org_id)
    body = fields.get("Body", "").strip()
    if sender and body:
        await record_inbound(
            session, org_id=org_id, channel=channel, handle=sender, body=body,
            contact_name=fields.get("ProfileName") or None,
            external_id=fields.get("MessageSid") or None,
        )
    return Response(content="<Response/>", media_type="application/xml")


@router.post("/webhooks/{org_id}/telegram")
async def telegram_inbound(org_id: str, request: Request, session: AsyncSession = Depends(get_session)):
    connection = await channels.get_connection(session, org_id, "telegram")
    credentials = channels.decrypt_credentials(connection) if connection else {}
    expected = credentials.get("webhook_secret", "")
    supplied = request.headers.get("x-telegram-bot-api-secret-token", "")
    if not expected or not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=403, detail="Invalid provider signature.")
    await _check_org(session, org_id)
    try:
        payload = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(status_code=400, detail="Invalid Telegram update.")
    message = payload.get("message") or payload.get("edited_message") or {}
    sender = message.get("from") or {}
    chat = message.get("chat") or {}
    body = str(message.get("text") or "").strip()
    if body and chat.get("id") is not None:
        await record_inbound(
            session, org_id=org_id, channel=Channel.TELEGRAM, handle=str(chat["id"]), body=body,
            contact_name=" ".join(filter(None, [sender.get("first_name"), sender.get("last_name")])) or None,
            external_id=str(message.get("message_id")) if message.get("message_id") is not None else None,
        )
    return {"ok": True}


@router.post("/webhooks/{org_id}/line")
async def line_inbound(
    org_id: str, request: Request, hook: str = "", session: AsyncSession = Depends(get_session),
):
    connection = await channels.get_connection(session, org_id, "line")
    credentials = channels.decrypt_credentials(connection) if connection else {}
    channel_secret = credentials.get("channel_secret", "")
    raw = await request.body()
    signature = request.headers.get("x-line-signature", "")
    expected = base64.b64encode(hmac.new(channel_secret.encode(), raw, hashlib.sha256).digest()).decode() if channel_secret else ""
    if (
        not connection or not hook or not connection.webhook_token
        or not hmac.compare_digest(hook, connection.webhook_token)
        or not expected or not hmac.compare_digest(expected, signature)
    ):
        raise HTTPException(status_code=403, detail="Invalid provider signature.")
    await _check_org(session, org_id)
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(status_code=400, detail="Invalid LINE event.")
    for event in payload.get("events", []):
        message = event.get("message") or {}
        source = event.get("source") or {}
        body = str(message.get("text") or "").strip()
        sender = source.get("userId")
        if body and sender:
            await record_inbound(
                session, org_id=org_id, channel=Channel.LINE, handle=str(sender), body=body,
                external_id=str(message.get("id") or event.get("webhookEventId") or "") or None,
            )
    return {"ok": True}


@router.post("/webhooks/{org_id}/twilio/status")
async def twilio_status(org_id: str, request: Request, session: AsyncSession = Depends(get_session)):
    raw = (await request.body()).decode("utf-8", errors="replace")
    fields = dict(parse_qsl(raw, keep_blank_values=True))
    channel = "whatsapp" if fields.get("To", "").startswith("whatsapp:") else "sms"
    credentials = await channels.get_credentials(session, org_id, channel)
    if not _verify_twilio(_public_url(request), request.headers.get("x-twilio-signature", ""), fields, (credentials or {}).get("auth_token", "")):
        raise HTTPException(status_code=403, detail="Invalid provider signature.")
    await _check_org(session, org_id)
    sid = fields.get("MessageSid") or fields.get("SmsSid")
    status = (fields.get("MessageStatus") or fields.get("SmsStatus") or "").lower()
    if sid:
        message = (await session.execute(select(InboxMessage).where(InboxMessage.organization_id == org_id, InboxMessage.external_id == sid))).scalar_one_or_none()
        if message:
            delivery_changed = False
            if status == "delivered":
                message.delivery_status = "delivered"
                delivery_changed = True
            elif status in {"failed", "undelivered"} and message.delivery_status != "delivered":
                message.delivery_status = "failed"
                delivery_changed = True
            elif status in {"sent", "queued", "accepted", "scheduled"} and message.delivery_status in {"sending", "queued"}:
                message.delivery_status = "sent"
            message.delivery_error = fields.get("ErrorCode") if message.delivery_status == "failed" else None
            session.add(message)
            if status in {"delivered", "failed", "undelivered"}:
                lead = (await session.execute(select(Lead).where(
                    Lead.organization_id == org_id,
                    Lead.first_contact_external_id == sid,
                ).limit(1))).scalar_one_or_none()
                if lead and not (lead.first_contact_delivery_status == "delivered" and status != "delivered"):
                    lead.first_contact_delivery_status = "delivered" if status == "delivered" else "failed"
                    session.add(lead)
            if delivery_changed:
                await events.inbox_changed(org_id, conversation_id=message.conversation_id, action="delivery_status")
        campaign_delivery = (await session.execute(select(CampaignDelivery).where(
            CampaignDelivery.organization_id == org_id,
            CampaignDelivery.provider_message_id == sid,
        ))).scalar_one_or_none()
        if campaign_delivery:
            _apply_campaign_sms_status(campaign_delivery, status, fields.get("ErrorCode"))
            session.add(campaign_delivery)
    return {"ok": True}


@router.post("/webhooks/{org_id}/twilio/voice")
async def twilio_voice(org_id: str, request: Request, session: AsyncSession = Depends(get_session)):
    fields = dict(parse_qsl((await request.body()).decode("utf-8", errors="replace"), keep_blank_values=True))
    credentials = await channels.get_credentials(session, org_id, "sms")
    if not _verify_twilio(_public_url(request), request.headers.get("x-twilio-signature", ""), fields, (credentials or {}).get("auth_token", "")):
        raise HTTPException(status_code=403, detail="Invalid provider signature.")
    await _check_org(session, org_id)
    forward_to = (credentials or {}).get("forward_to_number")
    if not forward_to:
        raise HTTPException(status_code=503, detail="Call forwarding is not configured for this workspace.")
    action_url = f"{settings.inbox_public_webhook_base_url.rstrip('/')}/api/v1/inbox/webhooks/{org_id}/twilio/voice/status"
    twiml = (
        "<Response><Dial answerOnBridge=\"true\" timeout=\"20\" "
        f"action=\"{escape(action_url, quote=True)}\" method=\"POST\">"
        f"<Number>{escape(forward_to)}</Number></Dial></Response>"
    )
    return Response(content=twiml, media_type="application/xml")


@router.post("/webhooks/{org_id}/twilio/voice/status")
async def twilio_voice_status(org_id: str, request: Request, session: AsyncSession = Depends(get_session)):
    fields = dict(parse_qsl((await request.body()).decode("utf-8", errors="replace"), keep_blank_values=True))
    credentials = await channels.get_credentials(session, org_id, "sms")
    if not _verify_twilio(_public_url(request), request.headers.get("x-twilio-signature", ""), fields, (credentials or {}).get("auth_token", "")):
        raise HTTPException(status_code=403, detail="Invalid provider signature.")
    await _check_org(session, org_id)
    status = fields.get("DialCallStatus", "").lower()
    caller = fields.get("Caller", "").strip()
    call_sid = fields.get("CallSid", "").strip()
    if status not in {"busy", "no-answer", "failed", "canceled"} or not caller.startswith("+") or not call_sid:
        return Response(content="<Response/>", media_type="application/xml")

    # shortcut: only known lead callers create a callback task; add member callback cases when call logging supports members.
    lead = (await session.execute(select(Lead).where(
        Lead.organization_id == org_id,
        Lead.phone == caller,
        Lead.stage.not_in(("joined", "lost")),
    ).order_by(Lead.created_at.desc()).limit(1))).scalar_one_or_none()
    if lead is not None:
        owner_id = (await session.execute(select(OrganizationMember.user_id).where(
            OrganizationMember.organization_id == org_id,
            OrganizationMember.role == Role.OWNER,
        ).limit(1))).scalar_one_or_none()
        if owner_id:
            claim = await idempotency_service.claim(
                session, key=call_sid, endpoint=f"inbox.twilio_missed_call:{lead.id}",
                body={"call_sid": call_sid, "lead_id": lead.id},
                organization_id=org_id, user_id=owner_id,
            )
            if claim.claimed:
                result = await leads_service.log_missed_call(
                    session, org_id=org_id, lead_id=lead.id, actor_id=owner_id,
                    idempotency_key=call_sid,
                )
                from app.schemas.leads import LeadMissedCallOut

                output = LeadMissedCallOut(**result)
                await idempotency_service.complete(
                    session, claim.record, code=200, body=output.model_dump_json(),
                )
    return Response(content="<Response/>", media_type="application/xml")


@router.get("/webhooks/{org_id}/meta/{channel}")
async def meta_verify(org_id: str, channel: str, request: Request, hook: str = "", session: AsyncSession = Depends(get_session)):
    if channel not in {"instagram", "messenger"}:
        raise HTTPException(status_code=404, detail="Unknown Meta inbox channel.")
    credentials = await channels.get_credentials(session, org_id, channel)
    query = request.query_params
    connection = await channels.get_connection(session, org_id, channel)
    hook_ok = bool(connection and connection.webhook_token and hmac.compare_digest(hook, connection.webhook_token))
    if credentials and hook_ok and query.get("hub.mode") == "subscribe" and hmac.compare_digest(query.get("hub.verify_token", ""), credentials.get("verify_token", "")):
        return Response(content=query.get("hub.challenge", ""), media_type="text/plain")
    raise HTTPException(status_code=403, detail="Invalid webhook verification token.")


@router.post("/webhooks/{org_id}/meta/{channel}")
async def meta_inbound(org_id: str, channel: str, request: Request, hook: str = "", session: AsyncSession = Depends(get_session)):
    if channel not in {"instagram", "messenger"}:
        raise HTTPException(status_code=404, detail="Unknown Meta inbox channel.")
    credentials = await channels.get_credentials(session, org_id, channel)
    raw = await request.body()
    signature = request.headers.get("x-hub-signature-256", "")
    expected = "sha256=" + hmac.new((credentials or {}).get("app_secret", "").encode(), raw, hashlib.sha256).hexdigest()
    connection = await channels.get_connection(session, org_id, channel)
    hook_ok = bool(connection and connection.webhook_token and hmac.compare_digest(hook, connection.webhook_token))
    if not credentials or not credentials.get("app_secret") or not hook_ok or not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=403, detail="Invalid provider signature.")
    await _check_org(session, org_id)
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(status_code=400, detail="Invalid Meta event.")
    if not isinstance(payload, dict) or not isinstance(payload.get("entry", []), list):
        raise HTTPException(status_code=400, detail="Invalid Meta event.")
    captured_leads = []
    for entry in payload.get("entry", []):
        if not isinstance(entry, dict) or str(entry.get("id", "")) != str(credentials.get("sender_id", "")):
            continue
        if channel == "messenger":
            from app.services.lead_capture_service import capture_meta_lead

            changes = entry.get("changes") or []
            if not isinstance(changes, list):
                raise HTTPException(status_code=400, detail="Invalid Meta changes.")
            for change in changes:
                if isinstance(change, dict) and change.get("field") == "leadgen" and isinstance(change.get("value"), dict):
                    lead_id = await capture_meta_lead(session, org_id=org_id, credentials=credentials, value=change["value"])
                    if lead_id:
                        captured_leads.append(lead_id)
        for event in entry.get("messaging", []):
            message = event.get("message") or {}
            sender = (event.get("sender") or {}).get("id")
            body = str(message.get("text") or "").strip()
            if sender and body and not message.get("is_echo"):
                await record_inbound(session, org_id=org_id, channel=Channel(channel), handle=str(sender), body=body, external_id=str(message.get("mid") or "") or None)
    if captured_leads:
        await session.commit()
        await events.publish(org_id, "lead.changed", {"lead_ids": list(dict.fromkeys(captured_leads))})
    return {"ok": True}


def _verify_wechat_signature(token: str, signature: str, timestamp: str, nonce: str) -> bool:
    expected = hashlib.sha1("".join(sorted([token, timestamp, nonce])).encode()).hexdigest()
    return bool(token and signature and hmac.compare_digest(expected, signature))


@router.get("/webhooks/{org_id}/wechat")
async def wechat_verify(org_id: str, request: Request, hook: str = "", session: AsyncSession = Depends(get_session)):
    connection = await channels.get_connection(session, org_id, "wechat")
    credentials = channels.decrypt_credentials(connection) if connection else {}
    query = request.query_params
    if not connection or not hook or not connection.webhook_token or not hmac.compare_digest(hook, connection.webhook_token):
        raise HTTPException(status_code=403, detail="Invalid webhook token.")
    if _verify_wechat_signature(credentials.get("verify_token", ""), query.get("signature", ""), query.get("timestamp", ""), query.get("nonce", "")):
        return Response(content=query.get("echostr", ""), media_type="text/plain")
    raise HTTPException(status_code=403, detail="Invalid WeChat signature.")


@router.post("/webhooks/{org_id}/wechat")
async def wechat_inbound(org_id: str, request: Request, hook: str = "", session: AsyncSession = Depends(get_session)):
    connection = await channels.get_connection(session, org_id, "wechat")
    credentials = channels.decrypt_credentials(connection) if connection else {}
    query = request.query_params
    if not connection or not hook or not connection.webhook_token or not hmac.compare_digest(hook, connection.webhook_token) or not _verify_wechat_signature(credentials.get("verify_token", ""), query.get("signature", ""), query.get("timestamp", ""), query.get("nonce", "")):
        raise HTTPException(status_code=403, detail="Invalid WeChat signature.")
    await _check_org(session, org_id)
    try:
        root = ET.fromstring(await request.body())
    except ET.ParseError:
        raise HTTPException(status_code=400, detail="Invalid WeChat XML message.")
    sender = root.findtext("FromUserName")
    body = root.findtext("Content")
    if sender and body:
        await record_inbound(session, org_id=org_id, channel=Channel.WECHAT, handle=sender, body=body.strip(), external_id=root.findtext("MsgId"))
    return Response(content="success", media_type="text/plain")


@router.post("/webhooks/{org_id}/resend")
async def resend_inbound(org_id: str, request: Request, session: AsyncSession = Depends(get_session)):
    connection = await channels.get_connection(session, org_id, "email")
    credentials = channels.decrypt_credentials(connection) if connection else {}
    secret = credentials.get("inbound_webhook_secret", "")
    raw = await request.body()
    msg_id = request.headers.get("svix-id", "")
    timestamp = request.headers.get("svix-timestamp", "")
    signature = request.headers.get("svix-signature", "")
    try:
        timestamp_num = int(timestamp)
        key = secret.removeprefix("whsec_")
        key_bytes = base64.b64decode(key + "=" * (-len(key) % 4))
        expected = base64.b64encode(hmac.new(key_bytes, f"{msg_id}.{timestamp}.{raw.decode()}".encode(), hashlib.sha256).digest()).decode()
        valid = bool(secret and abs(time.time() - timestamp_num) <= 300 and any(hmac.compare_digest(item.removeprefix("v1,"), expected) for item in signature.split()))
    except (ValueError, UnicodeDecodeError):
        valid = False
    if not valid:
        raise HTTPException(status_code=403, detail="Invalid Resend webhook signature.")
    await _check_org(session, org_id)
    try:
        event = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(status_code=400, detail="Invalid Resend event.")
    if event.get("type") != "email.received":
        return {"ok": True}
    data = event.get("data") or {}
    email_id = str(data.get("email_id") or "")
    sender = parseaddr(str(data.get("from") or ""))[1].strip().lower()
    subject = str(data.get("subject") or "")[:300]
    body = str(data.get("text") or "").strip()
    if not body and email_id and credentials.get("resend_api_key"):
        try:
            async with httpx.AsyncClient(timeout=12) as client:
                response = await client.get(f"https://api.resend.com/emails/receiving/{email_id}", headers={"Authorization": f"Bearer {credentials['resend_api_key']}"})
            response.raise_for_status()
            received = response.json()
            body = str(received.get("text") or "").strip()
            if not body and received.get("html"):
                body = re.sub(r"<[^>]+>", " ", str(received["html"]))
                body = re.sub(r"\s+", " ", body).strip()
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=503, detail="Could not retrieve the received email content from Resend.") from exc
    if sender and (body or subject):
        thread = await record_inbound(session, org_id=org_id, channel=Channel.EMAIL, handle=sender, body=body or f"Subject: {subject}", contact_name=None, external_id=email_id or data.get("message_id"))
        conv = await session.get(InboxConversation, thread["id"])
        if conv and subject:
            conv.subject = subject
            session.add(conv)
    return {"ok": True}
