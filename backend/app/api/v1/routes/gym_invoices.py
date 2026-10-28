"""Gym admin API for member invoices and receivables."""


from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_org, get_session, require_capability, require_writable_org
from app.core.permissions import Capability
from app.core.tenancy import IDEMPOTENCY_HEADER, TenantContext
from app.models.gym_invoice import GymInvoice
from app.models.membership import OrganizationMember
from app.models.organization import Organization
from app.models.user import User
from app.schemas.gym_invoices import (
    GymInvoiceCreate,
    GymInvoiceOut,
    GymInvoicePaymentCreate,
    GymInvoiceVoid,
)
from app.services import gym_invoices_service as service

router = APIRouter()


async def gym_only(org: Organization = Depends(get_org)) -> Organization:
    if org.industry != "gym":
        raise HTTPException(status_code=404, detail="Gym invoices are not available for this workspace.")
    return org


async def writable_gym_only(org: Organization = Depends(require_writable_org)) -> Organization:
    if org.industry != "gym":
        raise HTTPException(status_code=404, detail="Gym invoices are not available for this workspace.")
    return org


async def _out(session: AsyncSession, invoice: GymInvoice) -> GymInvoiceOut:
    member = await session.get(OrganizationMember, invoice.member_id)
    user = await session.get(User, member.user_id) if member else None
    paid = await service._paid(session, invoice)
    return GymInvoiceOut(
        id=invoice.id, invoice_number=invoice.invoice_number, member_id=invoice.member_id,
        member_name=(member.display_name or user.full_name) if member and user else None,
        member_email=user.email if user else None, description=invoice.description,
        issue_date=invoice.issue_date, due_date=invoice.due_date,
        status=service.displayed_status(invoice, paid), subtotal=invoice.subtotal,
        tax_amount=invoice.tax_amount, total=invoice.total, paid_amount=paid,
        balance_due=max(0, invoice.total - paid), currency=invoice.currency,
        notes=invoice.notes, email_accepted=invoice.email_accepted,
    )


@router.get("", response_model=list[GymInvoiceOut])
async def list_invoices(
    _org: Organization = Depends(gym_only),
    ctx: TenantContext = Depends(require_capability(Capability.MANAGE_GYM_INVOICES)),
    session: AsyncSession = Depends(get_session),
):
    rows = await service.list_invoices(session, org_id=ctx.org_id)
    return [GymInvoiceOut(**row) for row in rows]


@router.post("", response_model=GymInvoiceOut, status_code=201,
             dependencies=[Depends(writable_gym_only)])
async def create_invoice(
    data: GymInvoiceCreate,
    ctx: TenantContext = Depends(require_capability(Capability.MANAGE_GYM_INVOICES)),
    org: Organization = Depends(writable_gym_only),
    session: AsyncSession = Depends(get_session),
):
    invoice = await service.create_invoice(session, org=org, data=data, actor_id=ctx.user_id)
    return await _out(session, invoice)


@router.post("/{invoice_id}/send", response_model=GymInvoiceOut,
             dependencies=[Depends(writable_gym_only)])
async def send_invoice(
    invoice_id: str,
    ctx: TenantContext = Depends(require_capability(Capability.MANAGE_GYM_INVOICES)),
    session: AsyncSession = Depends(get_session),
    _org: Organization = Depends(writable_gym_only),
):
    invoice = await service.send_invoice(session, org_id=ctx.org_id, invoice_id=invoice_id, actor_id=ctx.user_id)
    return await _out(session, invoice)


@router.post("/{invoice_id}/payments", response_model=GymInvoiceOut,
             dependencies=[Depends(writable_gym_only)])
async def record_payment(
    invoice_id: str,
    data: GymInvoicePaymentCreate,
    idempotency_key: str = Header(default="", alias=IDEMPOTENCY_HEADER),
    ctx: TenantContext = Depends(require_capability(Capability.MANAGE_GYM_INVOICES)),
    session: AsyncSession = Depends(get_session),
    _org: Organization = Depends(writable_gym_only),
):
    invoice = await service.record_payment(
        session, org_id=ctx.org_id, invoice_id=invoice_id, amount=data.amount,
        method=data.method, note=data.note, paid_on=data.paid_on,
        actor_id=ctx.user_id, idempotency_key=idempotency_key,
    )
    return await _out(session, invoice)


@router.post("/{invoice_id}/void", response_model=GymInvoiceOut,
             dependencies=[Depends(writable_gym_only)])
async def void_invoice(
    invoice_id: str,
    data: GymInvoiceVoid,
    ctx: TenantContext = Depends(require_capability(Capability.MANAGE_GYM_INVOICES)),
    session: AsyncSession = Depends(get_session),
    _org: Organization = Depends(writable_gym_only),
):
    invoice = await service.void_invoice(
        session, org_id=ctx.org_id, invoice_id=invoice_id, actor_id=ctx.user_id, reason=data.reason
    )
    return await _out(session, invoice)
