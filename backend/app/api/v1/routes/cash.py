"""Cash payment logging & reconciliation API routes (Section 11)."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Header
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.api.deps import get_session, require_capability, require_writable_org
from app.core.permissions import Capability
from app.core.tenancy import IDEMPOTENCY_HEADER, TenantContext
from app.core.constants import PaymentMethod
from app.models.membership import OrganizationMember
from app.models.payment import Payment
from app.models.plan import MembershipPlan
from app.models.user import User
from app.schemas.cash import (
    CashMemberOut,
    CashHistoryOut,
    CashPaymentLog,
    CashQuoteRequest,
    CashPaymentOut,
    ReconciliationOut,
    ReconciliationRequest,
)
from app.services import cash_service as cash
from app.services import idempotency_service
from app.services.pricing_service import quote_member_payment
from app.schemas.promotions import PriceQuoteOut
from fastapi import HTTPException

router = APIRouter()


@router.get("/history", response_model=list[CashHistoryOut])
async def cash_history(
    ctx: TenantContext = Depends(require_capability(Capability.LOG_CASH_PAYMENT)),
    session: AsyncSession = Depends(get_session),
):
    """Recent offline payments for the staff member's current organization."""
    rows = await session.execute(
        select(Payment, User.full_name, MembershipPlan.name)
        .outerjoin(OrganizationMember, Payment.member_id == OrganizationMember.id)
        .outerjoin(User, OrganizationMember.user_id == User.id)
        .outerjoin(MembershipPlan, Payment.plan_id == MembershipPlan.id)
        .where(
            Payment.organization_id == ctx.org_id,
            Payment.logged_by.is_not(None),
            Payment.method.in_([PaymentMethod.CASH, PaymentMethod.BANK_TRANSFER, PaymentMethod.MOBILE_WALLET]),
        )
        .order_by(Payment.created_at.desc())
        .limit(200)
    )
    return [CashHistoryOut(
        id=payment.id, member_name=member_name, plan_name=plan_name,
        amount=payment.amount, currency=payment.currency, method=payment.method.value,
        status=payment.status.value, paid_at=payment.paid_at,
    ) for payment, member_name, plan_name in rows]


def _cash_member(m, u) -> CashMemberOut:
    return CashMemberOut(
        member_id=m.id, full_name=u.full_name, email=u.email,
        member_status=m.member_status.value, role=m.role.value,
    )


@router.get("/members", response_model=list[CashMemberOut])
async def search_cash_members(
    q: str | None = None,
    ctx: TenantContext = Depends(require_capability(Capability.LOG_CASH_PAYMENT)),
    session: AsyncSession = Depends(get_session),
):
    rows = await cash.search_members(session, org_id=ctx.org_id, q=q)
    return [_cash_member(m, u) for m, u in rows]


@router.post("/log", response_model=CashPaymentOut, status_code=201, dependencies=[Depends(require_writable_org)])
async def log_cash_payment(
    data: CashPaymentLog,
    idempotency_key: str = Header(default="", alias=IDEMPOTENCY_HEADER),
    ctx: TenantContext = Depends(require_capability(Capability.LOG_CASH_PAYMENT)),
    session: AsyncSession = Depends(get_session),
):
    claim = await idempotency_service.claim(
        session,
        key=idempotency_key,
        endpoint="cash.log",
        body=data.model_dump(mode="json"),
        organization_id=ctx.org_id,
        user_id=ctx.user_id,
    )
    if not claim.claimed:
        return CashPaymentOut.model_validate(json.loads(claim.cached_response or "{}"))
    payment, member, pdf_url = await cash.log_cash_payment(
        session, org_id=ctx.org_id, data=data, staff_user_id=ctx.user_id
    )
    output = CashPaymentOut(
        payment_id=payment.id, member_id=member.id, amount=payment.amount,
        method=payment.method.value, member_status=member.member_status.value,
        receipt_pdf_url=pdf_url,
    )
    await idempotency_service.complete(
        session, claim.record, code=201, body=output.model_dump_json()
    )
    return output


@router.post("/quote", response_model=PriceQuoteOut)
async def cash_quote(
    data: CashQuoteRequest,
    ctx: TenantContext = Depends(require_capability(Capability.LOG_CASH_PAYMENT)),
    session: AsyncSession = Depends(get_session),
):
    member = await session.get(OrganizationMember, data.member_id)
    plan = await session.get(MembershipPlan, data.plan_id)
    if member is None or member.organization_id != ctx.org_id:
        raise HTTPException(status_code=404, detail="Member not found.")
    if plan is None or plan.organization_id != ctx.org_id:
        raise HTTPException(status_code=404, detail="Plan not found.")
    return await quote_member_payment(session, org_id=ctx.org_id, member_id=member.id,
                                      plan=plan, promo_code=data.promo_code)


@router.get("/payments/{payment_id}/receipt")
async def cash_payment_receipt(
    payment_id: str,
    ctx: TenantContext = Depends(require_capability(Capability.LOG_CASH_PAYMENT)),
    session: AsyncSession = Depends(get_session),
):
    """Download the proof-of-payment receipt for an offline payment."""
    pdf_bytes, filename = await cash.render_receipt(
        session, org_id=ctx.org_id, payment_id=payment_id
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/reconcile", response_model=ReconciliationOut, status_code=201, dependencies=[Depends(require_writable_org)])
async def reconcile(
    data: ReconciliationRequest,
    ctx: TenantContext = Depends(require_capability(Capability.LOG_CASH_PAYMENT)),
    session: AsyncSession = Depends(get_session),
):
    rec, alert = await cash.reconcile(
        session, org_id=ctx.org_id, business_date=data.business_date,
        counted_total=data.counted_total, performed_by=ctx.user_id, notes=data.notes,
    )
    return ReconciliationOut(
        id=rec.id, business_date=rec.business_date, system_total=rec.system_total,
        counted_total=rec.counted_total, discrepancy=rec.discrepancy,
        performed_by=rec.performed_by, alert_triggered=alert,
    )
