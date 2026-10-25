"""Audited accounting exports and payment dispute evidence for gym admins."""

import csv
import hashlib
import io
import json
import zipfile
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.api.deps import get_client_ip, get_session, require_capability
from app.core.permissions import Capability
from app.core.security import now_utc
from app.core.tenancy import TenantContext
from app.models.attendance import Attendance
from app.models.audit_log import AuditLog
from app.models.membership import OrganizationMember
from app.models.organization import Organization
from app.models.payment import Payment
from app.models.plan import MembershipPlan
from app.models.receipt import ReceiptUpload
from app.models.subscription import Subscription
from app.models.user import User
from app.services.audit_service import record_audit

router = APIRouter()


def period_bounds(start: date, end: date, zone_name: str) -> tuple[datetime, datetime]:
    if end < start or (end - start).days > 365 or end == date.max:
        raise HTTPException(status_code=422, detail="Choose a date range of at most 366 days, with the end on or after the start.")
    try:
        zone = ZoneInfo(zone_name)
    except ZoneInfoNotFoundError:
        zone = ZoneInfo("UTC")
    return tuple(datetime.combine(day, time.min, zone).astimezone(timezone.utc).replace(tzinfo=None)
                 for day in (start, end + timedelta(days=1)))


def csv_row(values: list) -> str:
    stream = io.StringIO()
    safe = []
    for value in values:
        text = "" if value is None else str(value)
        safe.append("'" + text if text.lstrip()[:1] in {"=", "+", "-", "@"} else text)
    csv.writer(stream).writerow(safe)
    return stream.getvalue()


@router.get("/payments.csv")
async def export_payments(
    request: Request,
    date_from: date, date_to: date,
    ctx: TenantContext = Depends(require_capability(Capability.VIEW_REVENUE_ANALYTICS)),
    session: AsyncSession = Depends(get_session),
):
    org = await session.get(Organization, ctx.org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Gym not found.")
    start, end = period_bounds(date_from, date_to, org.timezone or "UTC")
    paid_date = func.coalesce(Payment.paid_at, Payment.created_at)
    statement = select(Payment).where(
        Payment.organization_id == ctx.org_id, paid_date >= start, paid_date < end,
    ).order_by(paid_date, Payment.id).execution_options(yield_per=500)
    await record_audit(
        session, action="finance.payments_exported", organization_id=ctx.org_id,
        actor_user_id=ctx.user_id, entity_type="payment", ip_address=get_client_ip(request),
        metadata={"date_from": str(date_from), "date_to": str(date_to)},
    )

    async def content():
        yield "\ufeff" + csv_row(["payment_id", "paid_at_utc", "member_id", "kind", "method", "status",
                                  "currency", "gross_amount", "tax_amount", "lifetime_refunded_amount",
                                  "current_net_amount", "stripe_payment_intent_id", "stripe_charge_id"])
        rows = await session.stream_scalars(statement)
        async for payment in rows:
            gross = Decimal(str(payment.amount)).quantize(Decimal("0.01"))
            refunded = Decimal(str(payment.refunded_amount)).quantize(Decimal("0.01"))
            yield csv_row([payment.id, payment.paid_at or payment.created_at, payment.member_id,
                           payment.kind.value, payment.method.value, payment.status.value, payment.currency,
                           gross, Decimal(str(payment.tax_amount)).quantize(Decimal("0.01")), refunded,
                           gross - refunded, payment.stripe_payment_intent_id, payment.stripe_charge_id])

    return StreamingResponse(content(), media_type="text/csv", headers={
        "Content-Disposition": f'attachment; filename="payments-{date_from}-{date_to}.csv"',
        "Cache-Control": "no-store",
    })


@router.get("/payments/{payment_id}/evidence.zip")
async def payment_evidence(
    payment_id: str, request: Request,
    ctx: TenantContext = Depends(require_capability(Capability.VIEW_REVENUE_ANALYTICS)),
    session: AsyncSession = Depends(get_session),
):
    payment = await session.get(Payment, payment_id)
    if payment is None or payment.organization_id != ctx.org_id:
        raise HTTPException(status_code=404, detail="Payment not found.")
    member = await session.get(OrganizationMember, payment.member_id) if payment.member_id else None
    if member and member.organization_id != ctx.org_id:
        member = None
    user = await session.get(User, member.user_id) if member else None
    sub = await session.get(Subscription, payment.subscription_id) if payment.subscription_id else None
    if sub and (sub.organization_id != ctx.org_id or sub.member_id != payment.member_id):
        sub = None
    plan = await session.get(MembershipPlan, payment.plan_id) if payment.plan_id else None
    if plan and plan.organization_id != ctx.org_id:
        plan = None
    visits = []
    if member and sub:
        statement = select(Attendance).where(
            Attendance.organization_id == ctx.org_id, Attendance.member_id == member.id,
            Attendance.checked_in_at >= sub.started_at,
        )
        if sub.current_period_end:
            statement = statement.where(Attendance.checked_in_at <= sub.current_period_end)
        visits = (await session.execute(statement.order_by(Attendance.checked_in_at).limit(5001))).scalars().all()
    logs = (await session.execute(select(AuditLog).where(
        AuditLog.organization_id == ctx.org_id,
        AuditLog.entity_id.in_([payment.id] + ([payment.receipt_id] if payment.receipt_id else [])),
        AuditLog.entity_type.in_(["payment", "receipt"]),
    ).order_by(AuditLog.created_at).limit(5001))).scalars().all()
    receipt = await session.get(ReceiptUpload, payment.receipt_id) if payment.receipt_id else None
    if receipt and (receipt.organization_id != ctx.org_id or receipt.member_id != payment.member_id):
        receipt = None
    evidence = {
        "generated_at_utc": now_utc(), "organization_id": ctx.org_id,
        "payment": {"id": payment.id, "amount": str(payment.amount), "currency": payment.currency,
                    "status": payment.status.value, "method": payment.method.value,
                    "paid_at": payment.paid_at, "refunded_amount": str(payment.refunded_amount),
                    "stripe_payment_intent_id": payment.stripe_payment_intent_id, "stripe_charge_id": payment.stripe_charge_id,
                    "payer_contributions": payment.payer_contributions},
        "member": {"id": member.id, "name": member.display_name or (user.full_name if user else None),
                   "email": user.email if user else None} if member else None,
        "subscription": {"id": sub.id, "started_at": sub.started_at, "current_period_end": sub.current_period_end} if sub else None,
        "current_plan_terms": {"name": plan.name, "description": plan.public_description} if plan else None,
        "visits": [{"checked_in_at": row.checked_in_at, "method": row.method.value,
                    "source": row.source.value} for row in visits[:5000]],
        "audit_events": [{"action": row.action, "created_at": row.created_at, "actor_user_id": row.actor_user_id} for row in logs[:5000]],
        "receipt": {"id": receipt.id, "status": receipt.status.value, "reviewed_at": receipt.reviewed_at} if receipt else None,
        "limitations": {"visits_truncated": len(visits) > 5000, "audit_truncated": len(logs) > 5000,
                        "plan_terms_are_current": True, "provider_dispute_submission_included": False},
    }
    files = {"evidence.json": json.dumps(evidence, default=str, indent=2).encode()}
    if receipt and receipt.image_data:
        extension = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}.get(receipt.image_media_type)
        if extension:
            files[f"receipt.{extension}"] = receipt.image_data
    files["manifest.json"] = json.dumps({name: hashlib.sha256(data).hexdigest() for name, data in files.items()}, indent=2).encode()
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    await record_audit(
        session, action="payment.evidence_exported", organization_id=ctx.org_id,
        actor_user_id=ctx.user_id, entity_type="payment", entity_id=payment.id,
        ip_address=get_client_ip(request), metadata={"files": list(files)},
    )
    return Response(output.getvalue(), media_type="application/zip", headers={
        "Content-Disposition": f'attachment; filename="payment-{payment.id}-evidence.zip"',
        "Cache-Control": "no-store",
    })
