"""Tenant-scoped operating-expense ledger for gym owners and managers."""

from __future__ import annotations

import csv
import io
import hashlib
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, File, Header, HTTPException, Request, UploadFile
from fastapi.responses import Response, StreamingResponse
from starlette.concurrency import run_in_threadpool
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.api.deps import get_client_ip, get_session, require_capability, require_writable_org
from app.core.permissions import Capability
from app.core.security import now_utc
from app.core.tenancy import TenantContext
from app.models.operating_expense import OperatingExpense
from app.models.expense_receipt import ExpenseReceipt
from app.integrations.ocr import validate_image
from app.models.organization import Organization
from app.schemas.common import Message
from app.schemas.expenses import ExpenseCreate, ExpenseListOut, ExpenseOut, ExpenseVoid
from app.services import idempotency_service
from app.services.audit_service import record_audit

router = APIRouter()


def _csv_cell(value: object) -> str:
    text = "" if value is None else str(value)
    if text.lstrip(" \t\r\n")[:1] in {"=", "+", "-", "@"}:
        return f"'{text}"
    return text


@router.get("", response_model=ExpenseListOut)
async def list_expenses(
    date_from: date | None = None,
    date_to: date | None = None,
    ctx: TenantContext = Depends(require_capability(Capability.MANAGE_EXPENSES)),
    session: AsyncSession = Depends(get_session),
):
    if date_from and date_to and date_to < date_from:
        raise HTTPException(status_code=422, detail="End date must be on or after start date.")
    statement = select(OperatingExpense).where(
        OperatingExpense.organization_id == ctx.org_id,
    )
    if date_from:
        statement = statement.where(OperatingExpense.incurred_on >= date_from)
    if date_to:
        statement = statement.where(OperatingExpense.incurred_on <= date_to)
    # shortcut: latest 1,000 rows only; add cursor paging when ledger volume needs it.
    rows = (await session.execute(statement.order_by(
        OperatingExpense.incurred_on.desc(), OperatingExpense.created_at.desc()
    ).limit(1000))).scalars().all()
    receipt_ids = set((await session.execute(select(ExpenseReceipt.expense_id).where(
        ExpenseReceipt.organization_id == ctx.org_id, ExpenseReceipt.expense_id.in_([row.id for row in rows]),
    ))).scalars().all()) if rows else set()
    totals_statement = select(
        OperatingExpense.currency, func.sum(OperatingExpense.amount)
    ).where(
        OperatingExpense.organization_id == ctx.org_id,
        OperatingExpense.voided_at.is_(None),
    )
    if date_from:
        totals_statement = totals_statement.where(OperatingExpense.incurred_on >= date_from)
    if date_to:
        totals_statement = totals_statement.where(OperatingExpense.incurred_on <= date_to)
    totals_rows = (await session.execute(
        totals_statement.group_by(OperatingExpense.currency)
    )).all()
    return ExpenseListOut(
        items=[ExpenseOut.model_validate(row).model_copy(update={"has_receipt": row.id in receipt_ids}) for row in rows],
        totals_by_currency={currency: format(amount or Decimal("0.00"), ".2f")
                            for currency, amount in sorted(totals_rows)},
    )


@router.get("/export.csv")
async def export_expenses(
    request: Request,
    date_from: date | None = None,
    date_to: date | None = None,
    ctx: TenantContext = Depends(require_capability(Capability.MANAGE_EXPENSES)),
    session: AsyncSession = Depends(get_session),
):
    if date_from and date_to and date_to < date_from:
        raise HTTPException(status_code=422, detail="End date must be on or after start date.")
    statement = select(OperatingExpense).where(OperatingExpense.organization_id == ctx.org_id)
    if date_from:
        statement = statement.where(OperatingExpense.incurred_on >= date_from)
    if date_to:
        statement = statement.where(OperatingExpense.incurred_on <= date_to)
    statement = statement.order_by(OperatingExpense.incurred_on, OperatingExpense.created_at)
    result = await session.stream_scalars(statement.execution_options(yield_per=500))
    await record_audit(
        session, action="expense.exported", organization_id=ctx.org_id,
        actor_user_id=ctx.user_id, entity_type="operating_expense",
        ip_address=get_client_ip(request), user_agent=request.headers.get("user-agent"),
        metadata={"date_from": str(date_from) if date_from else None,
                  "date_to": str(date_to) if date_to else None},
    )
    await session.flush()

    async def rows():
        buffer = io.StringIO(newline="")
        writer = csv.writer(buffer)
        writer.writerow(["Date", "Category", "Description", "Vendor", "Amount", "Currency", "Status", "Void reason"])
        yield buffer.getvalue()
        async for expense in result:
            buffer = io.StringIO(newline="")
            writer = csv.writer(buffer)
            writer.writerow([_csv_cell(value) for value in (
                expense.incurred_on, expense.category, expense.description, expense.vendor,
                format(expense.amount, ".2f"), expense.currency,
                "voided" if expense.voided_at else "recorded", expense.void_reason,
            )])
            yield buffer.getvalue()

    return StreamingResponse(
        rows(), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="expense-ledger.csv"'},
    )


@router.post("", response_model=ExpenseOut, status_code=201,
             dependencies=[Depends(require_writable_org)])
async def create_expense(
    data: ExpenseCreate,
    request: Request,
    ctx: TenantContext = Depends(require_capability(Capability.MANAGE_EXPENSES)),
    session: AsyncSession = Depends(get_session),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    claim = await idempotency_service.claim(
        session, key=idempotency_key or "", endpoint="expenses.create",
        body=data.model_dump(mode="json"), organization_id=ctx.org_id, user_id=ctx.user_id,
    )
    if not claim.claimed:
        return ExpenseOut.model_validate_json(claim.cached_response or "{}")
    org = await session.get(Organization, ctx.org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Workspace not found.")
    expense = OperatingExpense(
        organization_id=ctx.org_id,
        category=data.category,
        description=data.description,
        vendor=data.vendor,
        amount=data.amount,
        currency=data.currency or org.default_currency.upper(),
        incurred_on=data.incurred_on,
        created_by=ctx.user_id,
    )
    session.add(expense)
    await session.flush()
    await record_audit(
        session, action="expense.created", organization_id=ctx.org_id,
        actor_user_id=ctx.user_id, entity_type="operating_expense", entity_id=expense.id,
        ip_address=get_client_ip(request), user_agent=request.headers.get("user-agent"),
        metadata={"category": expense.category, "amount": format(expense.amount, ".2f"), "currency": expense.currency},
    )
    output = ExpenseOut.model_validate(expense)
    await idempotency_service.complete(
        session, claim.record, code=201, body=output.model_dump_json(),
    )
    return output


@router.post("/{expense_id}/receipt", response_model=Message, status_code=201,
             dependencies=[Depends(require_writable_org)])
async def attach_receipt(
    expense_id: str,
    request: Request,
    file: UploadFile = File(...),
    idempotency_key: str = Header(default="", alias="Idempotency-Key"),
    ctx: TenantContext = Depends(require_capability(Capability.MANAGE_EXPENSES)),
    session: AsyncSession = Depends(get_session),
):
    expense = await session.get(OperatingExpense, expense_id, with_for_update=True, populate_existing=True)
    if expense is None or expense.organization_id != ctx.org_id:
        raise HTTPException(status_code=404, detail="Expense not found.")
    if expense.voided_at:
        raise HTTPException(status_code=409, detail="Receipt evidence cannot be added to a voided expense.")
    image = await file.read(5 * 1024 * 1024 + 1)
    if not image:
        raise HTTPException(status_code=422, detail="Choose a receipt image.")
    if len(image) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Expense receipts must be 5MB or smaller.")
    digest = hashlib.sha256(image).hexdigest()
    claim = await idempotency_service.claim(
        session, key=idempotency_key, endpoint=f"expense.receipt:{ctx.org_id}:{ctx.user_id}:{expense_id}",
        body={"sha256": digest}, organization_id=ctx.org_id, user_id=ctx.user_id,
    )
    if not claim.claimed:
        return Message.model_validate_json(claim.cached_response or "{}")
    existing = await session.get(ExpenseReceipt, expense_id)
    if existing and existing.organization_id != ctx.org_id:
        raise HTTPException(status_code=404, detail="Receipt evidence not found.")
    if existing and existing.sha256 != digest:
        raise HTTPException(status_code=409, detail="This expense already has receipt evidence. Original evidence cannot be overwritten.")
    if existing is None:
        try:
            media_type = await run_in_threadpool(validate_image, image)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        session.add(ExpenseReceipt(expense_id=expense_id, organization_id=ctx.org_id, image_data=image,
                                  media_type=media_type, sha256=digest, uploaded_by=ctx.user_id))
        await record_audit(
            session, action="expense.receipt_attached", organization_id=ctx.org_id, actor_user_id=ctx.user_id,
            entity_type="operating_expense", entity_id=expense_id,
            ip_address=get_client_ip(request), user_agent=request.headers.get("user-agent"),
            metadata={"sha256": digest, "media_type": media_type},
        )
    output = Message(message="Expense receipt attached.")
    await idempotency_service.complete(session, claim.record, code=201, body=output.model_dump_json())
    return output


@router.get("/{expense_id}/receipt")
async def download_receipt(
    expense_id: str,
    request: Request,
    ctx: TenantContext = Depends(require_capability(Capability.MANAGE_EXPENSES)),
    session: AsyncSession = Depends(get_session),
):
    expense = await session.get(OperatingExpense, expense_id)
    if expense is None or expense.organization_id != ctx.org_id:
        raise HTTPException(status_code=404, detail="Expense not found.")
    receipt = await session.get(ExpenseReceipt, expense_id)
    if receipt is None or receipt.organization_id != ctx.org_id:
        raise HTTPException(status_code=404, detail="Receipt evidence not found.")
    await record_audit(
        session, action="expense.receipt_downloaded", organization_id=ctx.org_id, actor_user_id=ctx.user_id,
        entity_type="operating_expense", entity_id=expense_id,
        ip_address=get_client_ip(request), user_agent=request.headers.get("user-agent"),
        metadata={"sha256": receipt.sha256},
    )
    extension = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}[receipt.media_type]
    return Response(receipt.image_data, media_type=receipt.media_type, headers={
        "Content-Disposition": f'attachment; filename="expense-receipt.{extension}"',
        "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
    })


@router.post("/{expense_id}/void", response_model=Message,
             dependencies=[Depends(require_writable_org)])
async def void_expense(
    expense_id: str,
    data: ExpenseVoid,
    request: Request,
    ctx: TenantContext = Depends(require_capability(Capability.MANAGE_EXPENSES)),
    session: AsyncSession = Depends(get_session),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    claim = await idempotency_service.claim(
        session, key=idempotency_key or "", endpoint=f"expenses.void:{expense_id}",
        body=data.model_dump(mode="json"), organization_id=ctx.org_id, user_id=ctx.user_id,
    )
    if not claim.claimed:
        return Message.model_validate_json(claim.cached_response or "{}")
    expense = await session.get(OperatingExpense, expense_id, with_for_update=True)
    if expense is None or expense.organization_id != ctx.org_id:
        raise HTTPException(status_code=404, detail="Expense not found.")
    if expense.voided_at is not None:
        raise HTTPException(status_code=409, detail="Expense is already voided.")
    expense.voided_at = now_utc()
    expense.voided_by = ctx.user_id
    expense.void_reason = data.reason
    session.add(expense)
    await record_audit(
        session, action="expense.voided", organization_id=ctx.org_id,
        actor_user_id=ctx.user_id, entity_type="operating_expense", entity_id=expense.id,
        ip_address=get_client_ip(request), user_agent=request.headers.get("user-agent"),
        metadata={"amount": format(expense.amount, ".2f"), "currency": expense.currency, "reason": data.reason},
    )
    output = Message(message="Expense voided.")
    await idempotency_service.complete(
        session, claim.record, code=200, body=output.model_dump_json(),
    )
    return output
