"""Audited accounting exports and payment dispute evidence for gym admins."""

import csv
import hashlib
import io
import json
import zipfile
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import Numeric, case, cast, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.api.deps import get_client_ip, get_session, require_capability
from app.core.permissions import Capability
from app.core.constants import IdempotencyStatus, PaymentKind, PaymentStatus
from app.core.security import now_utc
from app.core.tenancy import TenantContext
from app.integrations.stripe_connect import connect_stripe
from app.models.attendance import Attendance
from app.models.audit_log import AuditLog
from app.models.membership import OrganizationMember
from app.models.organization import Organization
from app.models.payment import Payment
from app.models.payment_refund import PaymentRefund
from app.models.operating_expense import OperatingExpense
from app.models.plan import MembershipPlan
from app.models.receipt import ReceiptUpload
from app.models.subscription import Subscription
from app.models.user import User
from app.services.audit_service import record_audit
from app.services import idempotency_service
from app.schemas.disputes import DisputeEvidenceRequest

router = APIRouter()


def operating_totals(receipts, refunds, legacy_refunds, expenses) -> dict:
    result = {}

    def bucket(currency):
        return result.setdefault(currency, {"gross_receipts": Decimal("0"), "taxes_collected": Decimal("0"),
                                            "refunds": Decimal("0"), "operating_expenses": Decimal("0"),
                                            "legacy_refund_payments": 0, "expense_categories": {}, "monthly_expenses": {}})

    for currency, gross, tax in receipts:
        row = bucket(currency)
        row["gross_receipts"] += Decimal(str(gross or 0))
        row["taxes_collected"] += Decimal(str(tax or 0))
    for currency, amount, legacy_count in refunds:
        row = bucket(currency)
        row["refunds"] += Decimal(str(amount or 0))
        row["legacy_refund_payments"] += int(legacy_count or 0)
    for currency, amount, count in legacy_refunds:
        row = bucket(currency)
        row["refunds"] += Decimal(str(amount or 0))
        row["legacy_refund_payments"] += int(count or 0)
    for currency, category, year, month, amount in expenses:
        row = bucket(currency)
        amount = Decimal(str(amount or 0))
        row["operating_expenses"] += amount
        row["expense_categories"][category] = row["expense_categories"].get(category, Decimal("0")) + amount
        period = f"{int(year):04}-{int(month):02}"
        row["monthly_expenses"][period] = row["monthly_expenses"].get(period, Decimal("0")) + amount
    for row in result.values():
        row["net_collections"] = row["gross_receipts"] - row["refunds"]
        row["operating_cash_surplus"] = row["net_collections"] - row["operating_expenses"]
        for key, value in row.items():
            if isinstance(value, Decimal):
                row[key] = format(value.quantize(Decimal("0.01")), ".2f")
            elif isinstance(value, dict):
                row[key] = {name: format(amount.quantize(Decimal("0.01")), ".2f") for name, amount in sorted(value.items())}
    return result


@router.get("/operating-report")
async def operating_report(
    date_from: date, date_to: date,
    ctx: TenantContext = Depends(require_capability(Capability.VIEW_REVENUE_ANALYTICS)),
    session: AsyncSession = Depends(get_session),
):
    org = await session.get(Organization, ctx.org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Gym not found.")
    start, end = period_bounds(date_from, date_to, org.timezone or "UTC")
    money_type = Numeric(18, 2)
    paid_date = func.coalesce(Payment.paid_at, Payment.created_at)
    kinds = [PaymentKind.MEMBER_FEE, PaymentKind.DAY_PASS]
    receipts = (await session.execute(select(
        Payment.currency, func.sum(cast(Payment.amount, money_type)), func.sum(cast(Payment.tax_amount, money_type)),
    ).where(Payment.organization_id == ctx.org_id, Payment.kind.in_(kinds),
            Payment.status.in_([PaymentStatus.SUCCEEDED, PaymentStatus.PARTIALLY_REFUNDED, PaymentStatus.REFUNDED]),
            paid_date >= start, paid_date < end).group_by(Payment.currency))).all()
    refunds = (await session.execute(select(
        PaymentRefund.currency, func.sum(PaymentRefund.amount),
        func.sum(case((PaymentRefund.source == "legacy_snapshot", 1), else_=0)),
    ).join(Payment, Payment.id == PaymentRefund.payment_id).where(
        PaymentRefund.organization_id == ctx.org_id, Payment.organization_id == ctx.org_id,
        Payment.kind.in_(kinds), PaymentRefund.occurred_at >= start, PaymentRefund.occurred_at < end,
    ).group_by(PaymentRefund.currency))).all()
    has_refund_ledger = select(PaymentRefund.id).where(
        PaymentRefund.payment_id == Payment.id, PaymentRefund.organization_id == ctx.org_id,
    ).exists()
    legacy = (await session.execute(select(Payment.currency,
        func.sum(cast(Payment.refunded_amount, money_type)), func.count(Payment.id),
    ).where(Payment.organization_id == ctx.org_id, Payment.kind.in_(kinds), Payment.refunded_amount > 0,
            Payment.refunded_at >= start, Payment.refunded_at < end, ~has_refund_ledger,
    ).group_by(Payment.currency))).all()
    year = func.extract("year", OperatingExpense.incurred_on)
    month = func.extract("month", OperatingExpense.incurred_on)
    expenses = (await session.execute(select(OperatingExpense.currency, OperatingExpense.category,
        year, month, func.sum(OperatingExpense.amount),
    ).where(OperatingExpense.organization_id == ctx.org_id, OperatingExpense.voided_at.is_(None),
            OperatingExpense.incurred_on >= date_from, OperatingExpense.incurred_on <= date_to,
    ).group_by(OperatingExpense.currency, OperatingExpense.category, year, month))).all()
    return {"date_from": date_from, "date_to": date_to, "by_currency": operating_totals(receipts, refunds, legacy, expenses),
            "basis": "Gym member/day-pass receipts include collected tax. Refunds include requests accepted by the provider, which may still be pending. Expenses use their recorded incurred dates. Payroll is included only when entered in the expense ledger. Legacy refunds use their last known refund date. These are recorded operating totals, not settled bank balances or accrual financial statements."}


def period_bounds(start: date, end: date, zone_name: str) -> tuple[datetime, datetime]:
    if end < start or (end - start).days > 365 or end == date.max:
        raise HTTPException(status_code=422, detail="Choose a date range of at most 366 days, with the end on or after the start.")
    try:
        zone = ZoneInfo(zone_name)
    except ZoneInfoNotFoundError:
        zone = ZoneInfo("UTC")
    return tuple(datetime.combine(day, time.min, zone).astimezone(timezone.utc).replace(tzinfo=None)
                 for day in (start, end + timedelta(days=1)))


@router.get("/disputes")
async def list_disputes(
    request: Request,
    ctx: TenantContext = Depends(require_capability(Capability.VIEW_REVENUE_ANALYTICS)),
    session: AsyncSession = Depends(get_session),
):
    """List recent disputes from the gym's own Stripe Connect account."""
    org = await session.get(Organization, ctx.org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Gym not found.")
    if not org.stripe_connect_account_id:
        raise HTTPException(status_code=409, detail="Connect a Stripe account to review disputes.")
    disputes = await connect_stripe.list_disputes(connected_account_id=org.stripe_connect_account_id)
    references = [
        (row.get("charge_id"), row.get("payment_intent_id")) for row in disputes
    ]
    predicates = [
        (Payment.stripe_charge_id == charge_id) | (Payment.stripe_payment_intent_id == intent_id)
        for charge_id, intent_id in references if charge_id or intent_id
    ]
    payment_by_ref = {}
    if predicates:
        payments = (await session.execute(select(Payment).where(
            Payment.organization_id == ctx.org_id, or_(*predicates),
        ))).scalars().all()
        for payment in payments:
            if payment.stripe_charge_id:
                payment_by_ref[payment.stripe_charge_id] = payment.id
            if payment.stripe_payment_intent_id:
                payment_by_ref[payment.stripe_payment_intent_id] = payment.id
    output = [{
        **dispute,
        "amount": format(Decimal(dispute["amount"]) / 100, ".2f"),
        "currency": str(dispute["currency"]).upper(),
        "payment_id": payment_by_ref.get(dispute.get("charge_id")) or
                      payment_by_ref.get(dispute.get("payment_intent_id")),
    } for dispute in disputes]
    await record_audit(
        session, action="finance.disputes_viewed", organization_id=ctx.org_id,
        actor_user_id=ctx.user_id, entity_type="payment_dispute", ip_address=get_client_ip(request),
        metadata={"count": len(output)},
    )
    return output


@router.post("/disputes/{dispute_id}/evidence")
async def submit_dispute_evidence(
    dispute_id: str,
    data: DisputeEvidenceRequest,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    ctx: TenantContext = Depends(require_capability(Capability.PROCESS_REFUNDS)),
    session: AsyncSession = Depends(get_session),
):
    """Stage or submit evidence to Stripe from the gym's Connect account."""
    org = await session.get(Organization, ctx.org_id)
    if org is None or not org.stripe_connect_account_id:
        raise HTTPException(status_code=409, detail="Connect a Stripe account before responding to disputes.")
    evidence = {
        key: value for key, value in data.model_dump(exclude={"submit"}, exclude_none=True).items()
        if str(value).strip()
    }
    if not evidence:
        raise HTTPException(status_code=422, detail="Add at least one evidence field.")
    claim = await idempotency_service.claim(
        session, key=idempotency_key, endpoint=f"finance.dispute-evidence:{ctx.org_id}:{dispute_id}",
        body={"evidence": evidence, "submit": data.submit}, organization_id=ctx.org_id,
        user_id=ctx.user_id,
    )
    if not claim.claimed:
        cached = json.loads(claim.cached_response or "{}")
        if claim.record.status == IdempotencyStatus.FAILED:
            raise HTTPException(status_code=claim.cached_code or 409,
                                detail=cached.get("detail", "The dispute evidence request failed."))
        return cached
    try:
        dispute = await connect_stripe.retrieve_dispute(
            connected_account_id=org.stripe_connect_account_id, dispute_id=dispute_id,
        )
    except Exception as exc:
        await idempotency_service.fail(session, claim.record, code=502,
                                       body='{"detail":"Could not reach Stripe to load this dispute."}')
        raise HTTPException(status_code=502, detail="Could not reach Stripe to load this dispute.") from exc
    if dispute is None:
        await idempotency_service.fail(session, claim.record, code=503,
                                       body='{"detail":"Stripe dispute access is unavailable."}')
        raise HTTPException(status_code=503, detail="Stripe dispute access is unavailable.")
    if dispute["status"] not in {"needs_response", "warning_needs_response"}:
        await idempotency_service.fail(session, claim.record, code=409,
                                       body='{"detail":"This dispute is no longer accepting evidence."}')
        raise HTTPException(status_code=409, detail="This dispute is no longer accepting evidence.")
    try:
        updated = await connect_stripe.submit_dispute_evidence(
            connected_account_id=org.stripe_connect_account_id, dispute_id=dispute_id,
            evidence=evidence, submit=data.submit, idempotency_key=idempotency_key,
        )
    except Exception as exc:
        await idempotency_service.fail(session, claim.record, code=502,
                                       body='{"detail":"Could not save dispute evidence with Stripe."}')
        raise HTTPException(status_code=502, detail="Could not save dispute evidence with Stripe.") from exc
    if updated is None:
        await idempotency_service.fail(session, claim.record, code=503,
                                       body='{"detail":"Stripe dispute access is unavailable."}')
        raise HTTPException(status_code=503, detail="Stripe dispute access is unavailable.")
    result = {"id": dispute_id, "status": updated["status"], "submitted": data.submit}
    await record_audit(
        session, action="finance.dispute_evidence_submitted" if data.submit else "finance.dispute_evidence_staged",
        organization_id=ctx.org_id, actor_user_id=ctx.user_id, entity_type="payment_dispute",
        entity_id=dispute_id, ip_address=get_client_ip(request),
        metadata={"evidence_fields": sorted(evidence), "status": updated["status"]},
    )
    await idempotency_service.complete(session, claim.record, code=200, body=json.dumps(result))
    return result


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
                                  "current_net_amount", "stripe_payment_intent_id", "stripe_charge_id", "tax_included"])
        rows = await session.stream_scalars(statement)
        async for payment in rows:
            gross = Decimal(str(payment.amount)).quantize(Decimal("0.01"))
            refunded = Decimal(str(payment.refunded_amount)).quantize(Decimal("0.01"))
            yield csv_row([payment.id, payment.paid_at or payment.created_at, payment.member_id,
                           payment.kind.value, payment.method.value, payment.status.value, payment.currency,
                           gross, Decimal(str(payment.tax_amount)).quantize(Decimal("0.01")), refunded,
                           gross - refunded, payment.stripe_payment_intent_id, payment.stripe_charge_id, payment.tax_included])

    return StreamingResponse(content(), media_type="text/csv", headers={
        "Content-Disposition": f'attachment; filename="payments-{date_from}-{date_to}.csv"',
        "Cache-Control": "no-store",
    })


@router.get("/refunds.csv")
async def export_refunds(
    request: Request,
    date_from: date, date_to: date,
    ctx: TenantContext = Depends(require_capability(Capability.VIEW_REVENUE_ANALYTICS)),
    session: AsyncSession = Depends(get_session),
):
    """Export dated refund movements for bookkeeping reconciliation."""
    org = await session.get(Organization, ctx.org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Gym not found.")
    start, end = period_bounds(date_from, date_to, org.timezone or "UTC")
    statement = select(PaymentRefund, Payment).join(
        Payment, Payment.id == PaymentRefund.payment_id,
    ).where(
        PaymentRefund.organization_id == ctx.org_id,
        Payment.organization_id == ctx.org_id,
        PaymentRefund.occurred_at >= start,
        PaymentRefund.occurred_at < end,
    ).order_by(PaymentRefund.occurred_at, PaymentRefund.id).execution_options(yield_per=500)
    await record_audit(
        session, action="finance.refunds_exported", organization_id=ctx.org_id,
        actor_user_id=ctx.user_id, entity_type="payment_refund", ip_address=get_client_ip(request),
        metadata={"date_from": str(date_from), "date_to": str(date_to)},
    )

    async def content():
        yield "\ufeff" + csv_row(["refund_id", "occurred_at_utc", "payment_id", "member_id", "kind",
                                  "method", "source", "currency", "refund_amount", "stripe_charge_id",
                                  "actor_user_id"])
        rows = await session.stream(statement)
        async for refund, payment in rows:
            yield csv_row([refund.id, refund.occurred_at, payment.id, payment.member_id,
                           payment.kind.value, payment.method.value, refund.source, refund.currency,
                           Decimal(str(refund.amount)).quantize(Decimal("0.01")),
                           payment.stripe_charge_id, refund.actor_user_id])

    return StreamingResponse(content(), media_type="text/csv", headers={
        "Content-Disposition": f'attachment; filename="refunds-{date_from}-{date_to}.csv"',
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
