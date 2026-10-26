"""Member invoice and receivable workflows for gym admins."""

from datetime import date, datetime, time
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import case, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.constants import PaymentKind, PaymentMethod, PaymentStatus, Role
from app.core.security import now_utc
from app.integrations.email import send_email_safe
from app.models.gym_invoice import GymInvoice
from app.models.membership import OrganizationMember
from app.models.organization import Organization
from app.models.payment import Payment
from app.models.user import User
from app.schemas.gym_invoices import GymInvoiceCreate
from app.services import idempotency_service
from app.services.audit_service import record_audit
from app.models.base import gen_uuid


def displayed_status(invoice: GymInvoice, paid: Decimal, today: date | None = None) -> str:
    if invoice.status in {"sent", "partial"} and invoice.due_date < (today or now_utc().date()):
        return "overdue"
    if invoice.status == "sent" and paid > 0:
        return "partial"
    return invoice.status


async def _paid(session: AsyncSession, invoice: GymInvoice) -> Decimal:
    amount = await session.scalar(select(func.coalesce(func.sum(case(
        (Payment.status == PaymentStatus.PARTIALLY_REFUNDED,
         Payment.amount - Payment.refunded_amount),
        else_=Payment.amount,
    )), 0)).where(
        Payment.organization_id == invoice.organization_id,
        Payment.gym_invoice_id == invoice.id,
        Payment.status.in_([PaymentStatus.SUCCEEDED, PaymentStatus.PARTIALLY_REFUNDED]),
    ))
    return Decimal(str(amount or 0)).quantize(Decimal("0.01"))


async def list_invoices(session: AsyncSession, *, org_id: str) -> list[dict]:
    rows = (await session.execute(
        select(GymInvoice, OrganizationMember, User)
        .join(OrganizationMember, (OrganizationMember.id == GymInvoice.member_id)
              & (OrganizationMember.organization_id == org_id))
        .join(User, User.id == OrganizationMember.user_id)
        .where(GymInvoice.organization_id == org_id)
        .order_by(GymInvoice.issue_date.desc(), GymInvoice.created_at.desc())
        .limit(1000)
    )).all()
    invoice_ids = [invoice.id for invoice, _member, _user in rows]
    paid_rows = (await session.execute(select(
        Payment.gym_invoice_id,
        func.sum(case(
            (Payment.status == PaymentStatus.PARTIALLY_REFUNDED,
             Payment.amount - Payment.refunded_amount),
            else_=Payment.amount,
        )),
    ).where(
        Payment.organization_id == org_id, Payment.gym_invoice_id.in_(invoice_ids),
        Payment.status.in_([PaymentStatus.SUCCEEDED, PaymentStatus.PARTIALLY_REFUNDED]),
    ).group_by(Payment.gym_invoice_id))).all() if invoice_ids else []
    paid_by_invoice = {invoice_id: Decimal(str(amount or 0)).quantize(Decimal("0.01"))
                       for invoice_id, amount in paid_rows}
    output = []
    for invoice, member, user in rows:
        paid = paid_by_invoice.get(invoice.id, Decimal("0.00"))
        output.append({
            "id": invoice.id, "invoice_number": invoice.invoice_number,
            "member_id": member.id, "member_name": member.display_name or user.full_name,
            "member_email": user.email, "description": invoice.description,
            "issue_date": invoice.issue_date, "due_date": invoice.due_date,
            "status": displayed_status(invoice, paid), "subtotal": invoice.subtotal,
            "tax_amount": invoice.tax_amount, "total": invoice.total, "paid_amount": paid,
            "balance_due": max(Decimal("0.00"), invoice.total - paid),
            "currency": invoice.currency, "notes": invoice.notes,
            "email_accepted": invoice.email_accepted,
        })
    return output


async def create_invoice(session: AsyncSession, *, org: Organization, data: GymInvoiceCreate,
                         actor_id: str) -> GymInvoice:
    member = await session.get(OrganizationMember, data.member_id)
    if member is None or member.organization_id != org.id or member.role != Role.MEMBER:
        raise HTTPException(status_code=404, detail="Gym member not found.")
    today = now_utc().date()
    if data.due_date < today:
        raise HTTPException(status_code=422, detail="Due date must be today or later.")
    currency = data.currency or org.default_currency.upper()
    if not currency.isalpha():
        raise HTTPException(status_code=422, detail="Currency must be a three-letter code.")
    invoice_id = gen_uuid()
    invoice = GymInvoice(
        id=invoice_id,
        organization_id=org.id, member_id=member.id,
        invoice_number=f"GINV-{today.year}-{invoice_id[:10].upper()}",
        description=data.description.strip(), issue_date=today, due_date=data.due_date,
        status="draft", subtotal=data.subtotal, tax_amount=data.tax_amount,
        total=(data.subtotal + data.tax_amount).quantize(Decimal("0.01")),
        currency=currency, notes=data.notes,
    )
    session.add(invoice)
    await session.flush()
    await record_audit(session, action="gym_invoice.created", organization_id=org.id,
                       actor_user_id=actor_id, entity_type="gym_invoice", entity_id=invoice.id,
                       new_values={"total": str(invoice.total), "currency": currency})
    return invoice


async def _owned(session: AsyncSession, *, org_id: str, invoice_id: str) -> GymInvoice:
    invoice = await session.get(GymInvoice, invoice_id, with_for_update=True)
    if invoice is None or invoice.organization_id != org_id:
        raise HTTPException(status_code=404, detail="Invoice not found.")
    member = await session.get(OrganizationMember, invoice.member_id)
    if member is None or member.organization_id != org_id:
        raise HTTPException(status_code=404, detail="Invoice not found.")
    return invoice


async def refresh_after_refund(session: AsyncSession, *, payment: Payment, actor_id: str | None) -> None:
    if not payment.gym_invoice_id:
        return
    invoice = await session.get(GymInvoice, payment.gym_invoice_id, with_for_update=True)
    if invoice is None or invoice.organization_id != payment.organization_id:
        return
    await session.flush()
    paid = await _paid(session, invoice)
    invoice.status = "paid" if paid >= invoice.total else "partial" if paid else "sent"
    session.add(invoice)
    await record_audit(
        session, action="gym_invoice.balance_reopened", organization_id=invoice.organization_id,
        actor_user_id=actor_id, entity_type="gym_invoice", entity_id=invoice.id,
        new_values={"balance_due": str(max(Decimal("0.00"), invoice.total - paid))},
    )


async def send_invoice(session: AsyncSession, *, org_id: str, invoice_id: str,
                       actor_id: str) -> GymInvoice:
    invoice = await _owned(session, org_id=org_id, invoice_id=invoice_id)
    if invoice.status != "draft":
        raise HTTPException(status_code=409, detail="Only draft invoices can be sent.")
    member = await session.get(OrganizationMember, invoice.member_id)
    user = await session.get(User, member.user_id) if member else None
    org = await session.get(Organization, org_id)
    if not member or not user or not org:
        raise HTTPException(status_code=404, detail="Invoice recipient not found.")
    invoice.status = "sent"
    invoice.email_accepted = await send_email_safe(
        user.email, f"Invoice {invoice.invoice_number} from {org.name}",
        f"{invoice.description}: {invoice.total:.2f} {invoice.currency} due {invoice.due_date.isoformat()}. "
        "Please contact the gym to arrange payment.",
    )
    session.add(invoice)
    await record_audit(session, action="gym_invoice.sent", organization_id=org_id,
                       actor_user_id=actor_id, entity_type="gym_invoice", entity_id=invoice.id,
                       metadata={"email_accepted": invoice.email_accepted})
    return invoice


async def record_payment(session: AsyncSession, *, org_id: str, invoice_id: str, amount: Decimal | None,
                         method: str, note: str | None, paid_on: date | None, actor_id: str,
                         idempotency_key: str) -> GymInvoice:
    invoice = await _owned(session, org_id=org_id, invoice_id=invoice_id)
    claim = await idempotency_service.claim(
        session, key=idempotency_key, endpoint=f"gym-invoice-payment:{invoice_id}",
        body={"amount": str(amount) if amount is not None else None, "method": method,
              "note": note, "paid_on": str(paid_on) if paid_on else None},
        organization_id=org_id, user_id=actor_id,
    )
    if not claim.claimed:
        return invoice
    if invoice.status not in {"sent", "partial"}:
        await idempotency_service.fail(session, claim.record, code=409,
                                       body='{"detail":"Invoice is not open for payment."}')
        raise HTTPException(status_code=409, detail="Invoice is not open for payment.")
    paid = await _paid(session, invoice)
    balance = invoice.total - paid
    value = (amount or balance).quantize(Decimal("0.01"))
    if value <= 0 or value > balance:
        await idempotency_service.fail(session, claim.record, code=422,
                                       body='{"detail":"Payment must not exceed the balance due."}')
        raise HTTPException(status_code=422, detail="Payment must not exceed the balance due.")
    try:
        payment_method = PaymentMethod(method)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Unsupported payment method.") from exc
    payment = Payment(
        organization_id=org_id, member_id=invoice.member_id, kind=PaymentKind.MEMBER_FEE,
        method=payment_method, status=PaymentStatus.SUCCEEDED, amount=float(value),
        currency=invoice.currency, note=note, logged_by=actor_id, gym_invoice_id=invoice.id,
        paid_at=now_utc() if paid_on is None else datetime.combine(paid_on, time.min),
        idempotency_key=idempotency_key,
    )
    session.add(payment)
    invoice.status = "paid" if value == balance else "partial"
    session.add(invoice)
    await session.flush()
    await record_audit(session, action="gym_invoice.payment_recorded", organization_id=org_id,
                       actor_user_id=actor_id, entity_type="gym_invoice", entity_id=invoice.id,
                       new_values={"amount": str(value), "method": method})
    await idempotency_service.complete(session, claim.record, code=201,
                                       body=f'{{"payment_id":"{payment.id}"}}')
    return invoice


async def void_invoice(session: AsyncSession, *, org_id: str, invoice_id: str,
                       actor_id: str) -> GymInvoice:
    invoice = await _owned(session, org_id=org_id, invoice_id=invoice_id)
    paid = await _paid(session, invoice)
    if invoice.status not in {"draft", "sent"} or paid:
        raise HTTPException(status_code=409, detail="Only unpaid draft or sent invoices can be voided.")
    invoice.status = "void"
    session.add(invoice)
    await record_audit(session, action="gym_invoice.voided", organization_id=org_id,
                       actor_user_id=actor_id, entity_type="gym_invoice", entity_id=invoice.id)
    return invoice
