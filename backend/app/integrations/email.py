"""Transactional email with SMTP / Resend providers and a dev-stub fallback.

Delivery precedence:
  1. SMTP (settings.smtp_active) — Gmail/any SMTP; delivers to ANY recipient with
     no verified sending domain, so it's the go-to for real dev delivery.
  2. Resend (settings.resend_api_key) — but the shared onboarding@resend.dev
     sender only reaches the account owner until a domain is verified.
  3. Stub — no provider: capture in the in-memory outbox + log. Tests/local flows
     read the outbox for verification codes.

``send_email`` raises ``EmailDeliveryError`` when a configured provider rejects a
message; ``send_email_safe`` swallows that for side-effect notifications.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

import resend

from app.core.config import settings

logger = logging.getLogger("email")

if settings.resend_api_key:
    resend.api_key = settings.resend_api_key


@dataclass
class SentEmail:
    to: str
    subject: str
    body: str
    attachments: list[str] = field(default_factory=list)


# Dev outbox — inspectable in tests / local dev.
outbox: list[SentEmail] = []


def _send_sync(params: resend.Emails.SendParams) -> dict:
    return resend.Emails.send(params)


def _html_from_text(body: str) -> str:
    """Render a plain-text body as a minimal, injection-safe HTML alternative.

    Everything is escaped, so an org name like ``Bell & Co`` can never break the
    markup. A paragraph that is a single space-free token is treated as a code the
    recipient has to type back and gets a monospace chip.
    """

    from html import escape

    paragraphs: list[str] = []
    for block in body.strip().split("\n\n"):
        block = block.strip()
        if not block:
            continue
        if len(block) <= 64 and " " not in block and "\n" not in block:
            paragraphs.append(
                f'<p style="margin:20px 0"><code style="background:#f1f5f9;'
                f'border:1px solid #e2e8f0;border-radius:6px;padding:8px 12px;'
                f'font-family:ui-monospace,Menlo,Consolas,monospace;'
                f'font-size:15px;letter-spacing:.04em;display:inline-block">'
                f"{escape(block)}</code></p>"
            )
            continue
        lines = "<br>".join(escape(line) for line in block.splitlines())
        paragraphs.append(f'<p style="margin:0 0 14px;line-height:1.6">{lines}</p>')

    return (
        '<div style="font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,'
        'sans-serif;font-size:15px;color:#0f172a;max-width:560px">'
        + "".join(paragraphs)
        + "</div>"
    )


def _send_smtp_sync(to: str, subject: str, body: str, smtp_config: dict | None = None) -> None:
    """Send one email over SMTP (e.g. Gmail). Blocking — run in a thread.

    Delivers real mail to ANY recipient without a verified sending domain, which
    is why it's the preferred path for local/dev with a Gmail App Password.

    ``Date`` and ``Message-ID`` are set explicitly: RFC 5322 requires both and
    ``smtplib`` adds neither. Gmail accepts such a message at the SMTP level
    (250) and then junk or spam-filters it, so the send looks successful to the
    caller while the recipient never sees it.
    """

    import smtplib
    from email.message import EmailMessage
    from email.utils import formatdate, make_msgid

    msg = EmailMessage()
    sender = (smtp_config or {}).get("from_email") or settings.smtp_sender
    host = (smtp_config or {}).get("host") or settings.smtp_host
    port = int((smtp_config or {}).get("port") or settings.smtp_port)
    username = (smtp_config or {}).get("username") or settings.smtp_user
    password = (smtp_config or {}).get("password") or settings.smtp_password
    use_tls = (smtp_config or {}).get("use_tls", settings.smtp_use_tls)
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = subject
    msg["Reply-To"] = sender
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=sender.rpartition("@")[2])
    msg.set_content(body)
    msg.add_alternative(_html_from_text(body), subtype="html")

    with smtplib.SMTP(host, port, timeout=15) as server:
        if use_tls:
            server.starttls()
        server.login(username, password)
        server.send_message(msg)


class EmailDeliveryError(Exception):
    """Raised when a configured provider rejects/fails to deliver an email.

    Carries the provider's message so user-facing flows (invites, verification)
    can surface *why* delivery failed instead of falsely reporting success.
    """


@dataclass(frozen=True)
class EmailSendResult:
    accepted: bool
    provider_message_id: str | None = None


async def send_email_tracked(
    to: str, subject: str, body: str, attachments: list[str] | None = None,
    smtp_config: dict | None = None,
) -> EmailSendResult:
    """Send an email and retain a provider ID when the sender supplies one.

    Raises ``EmailDeliveryError`` when a configured provider rejects the message
    (e.g. Resend's unverified-domain 403). Callers that must not fail on a
    delivery error (background fan-out) can catch it; user-facing flows let it
    propagate so the UI shows the real reason.

    Stub mode captures the message locally and returns an unaccepted result.
    """

    record = SentEmail(to=to, subject=subject, body=body, attachments=attachments or [])
    outbox.append(record)

    # SMTP first: it delivers to any recipient without a verified domain (Gmail
    # App Password), unlike Resend's shared test sender.
    if smtp_config or settings.smtp_active:
        try:
            await asyncio.to_thread(_send_smtp_sync, to, subject, body, smtp_config)
            logger.info("Email sent via SMTP to=%s subject=%s", to, subject)
            return EmailSendResult(True)
        except Exception as exc:
            logger.warning("SMTP send failed: to=%s error=%s", to, exc)
            raise EmailDeliveryError(str(exc)) from exc

    if settings.resend_api_key:
        try:
            params: resend.Emails.SendParams = {
                "from": settings.email_from,
                "to": [to],
                "subject": subject,
                "html": _html_from_text(body),
            }
            result = await asyncio.to_thread(_send_sync, params)
            provider_id = str(result.get("id") or "") or None
            logger.info("Email sent to=%s subject=%s id=%s", to, subject, provider_id or "?")
            return EmailSendResult(True, provider_id)
        except Exception as exc:
            # Do NOT swallow silently — that made failed invites look successful.
            logger.warning("Resend send failed: to=%s error=%s", to, exc)
            raise EmailDeliveryError(str(exc)) from exc

    # Stub mode only captures the message locally; nothing leaves the process.
    logger.info("[email-stub] to=%s subject=%s body=%s", to, subject, body)
    return EmailSendResult(False)


async def send_email(
    to: str, subject: str, body: str, attachments: list[str] | None = None,
    smtp_config: dict | None = None,
) -> bool:
    """Send an email; preserve the boolean contract for existing callers."""
    return (await send_email_tracked(to, subject, body, attachments, smtp_config)).accepted


async def send_email_tracked_safe(
    to: str, subject: str, body: str, attachments: list[str] | None = None,
) -> EmailSendResult:
    """Best-effort tracked send for background delivery workflows."""
    try:
        return await send_email_tracked(to, subject, body, attachments)
    except EmailDeliveryError:
        return EmailSendResult(False)


async def send_email_safe(
    to: str, subject: str, body: str, attachments: list[str] | None = None
) -> bool:
    """Best-effort send for side-effect notifications (receipts, pay stubs,
    welcome notes). Never raises: a delivery failure must not roll back the
    primary action that triggered it. Returns True only if delivered."""

    try:
        return await send_email(to, subject, body, attachments)
    except EmailDeliveryError:
        return False
