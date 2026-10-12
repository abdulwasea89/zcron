"""Cash payment logging & reconciliation API routes (Section 11)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.api.deps import get_session, require_capability, require_writable_org
from app.core.permissions import Capability
from app.core.tenancy import TenantContext
from app.core.constants import PaymentMethod
from app.models.membership import OrganizationMember
from app.models.payment import Payment
from app.models.plan import MembershipPlan
from app.models.user import User
from app.schemas.cash import (
    CashMemberOut,
    CashHistoryOut,
    CashPaymentLog,
    CashPaymentOut,
    ReconciliationOut,
    ReconciliationRequest,
)
from app.services import cash_service as cash

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
    ctx: TenantContext = Depends(require_capability(Capability.LOG_CASH_PAYMENT)),
    session: AsyncSession = Depends(get_session),
):
    payment, member, pdf_url = await cash.log_cash_payment(
        session, org_id=ctx.org_id, data=data, staff_user_id=ctx.user_id
    )
    return CashPaymentOut(
        payment_id=payment.id, member_id=member.id, amount=payment.amount,
        method=payment.method.value, member_status=member.member_status.value,
        receipt_pdf_url=pdf_url,
    )


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
