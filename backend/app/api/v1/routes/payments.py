"""Payment history & refund API routes (Sections 13, 16).

Refunds are admin-only and web-only (Security Rule #7) and require an
Idempotency-Key (Security Rule #2).
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.api.deps import get_session, get_tenant, require_capability, require_writable_org
from app.core.permissions import Capability
from app.core.tenancy import IDEMPOTENCY_HEADER, TenantContext
from app.models.membership import OrganizationMember
from app.schemas.payments import PaymentOut, RefundOut, RefundRequest
from app.services import payments_service as payments

router = APIRouter()


def _to_out(p) -> PaymentOut:
    return PaymentOut(
        id=p.id, member_id=p.member_id, plan_id=p.plan_id, kind=p.kind.value, method=p.method.value,
        stripe_payment_method_type=p.stripe_payment_method_type,
        status=p.status.value, amount=p.amount, tax_amount=p.tax_amount, tax_included=p.tax_included, currency=p.currency,
        plan_price_amount=p.plan_price_amount, joining_fee_amount=p.joining_fee_amount,
        discount_amount=p.discount_amount, promo_code=p.promo_code,
        refunded_amount=p.refunded_amount, paid_at=p.paid_at, created_at=p.created_at,
    )


async def _member_for(session: AsyncSession, org_id: str, user_id: str) -> OrganizationMember | None:
    return (
        await session.execute(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == org_id,
                OrganizationMember.user_id == user_id,
            )
        )
    ).scalar_one_or_none()


@router.get("/my", response_model=list[PaymentOut])
async def my_payments(
    ctx: TenantContext = Depends(get_tenant),
    session: AsyncSession = Depends(get_session),
):
    """A member's own payment history (self-service, member role)."""

    member = await _member_for(session, ctx.org_id, ctx.user_id)
    if member is None:
        raise HTTPException(status_code=404, detail="Membership not found.")
    return [
        _to_out(p)
        for p in await payments.list_payments(session, org_id=ctx.org_id, member_id=member.id)
    ]


@router.get("", response_model=list[PaymentOut])
async def list_payments(
    member_id: str | None = None,
    since: datetime | None = None,
    ctx: TenantContext = Depends(require_capability(Capability.VIEW_REVENUE_ANALYTICS)),
    session: AsyncSession = Depends(get_session),
):
    rows = await payments.list_payments(
        session, org_id=ctx.org_id, member_id=member_id, since=since
    )
    return [_to_out(payment) for payment in rows]


@router.post("/refund", response_model=RefundOut)
async def refund_payment(
    data: RefundRequest,
    idempotency_key: str = Header(default="", alias=IDEMPOTENCY_HEADER),
    ctx: TenantContext = Depends(require_capability(Capability.PROCESS_REFUNDS)),
    session: AsyncSession = Depends(get_session),
):
    payment = await payments.refund(
        session, org_id=ctx.org_id, payment_id=data.payment_id, amount=data.amount,
        reason=data.reason, idempotency_key=idempotency_key, actor_id=ctx.user_id,
    )
    return RefundOut(payment_id=payment.id, status=payment.status.value,
                     refunded_amount=payment.refunded_amount)


@router.post("/{payment_id}/verify", dependencies=[Depends(require_writable_org)])
async def verify_card_payment(
    payment_id: str,
    ctx: TenantContext = Depends(require_capability(Capability.PROCESS_REFUNDS)),
    session: AsyncSession = Depends(get_session),
):
    return await payments.verify_card_payment(session, org_id=ctx.org_id, payment_id=payment_id, actor_id=ctx.user_id)
