"""Tenant-scoped operating-expense ledger for gym owners and managers."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.api.deps import get_client_ip, get_session, require_capability, require_writable_org
from app.core.permissions import Capability
from app.core.security import now_utc
from app.core.tenancy import TenantContext
from app.models.operating_expense import OperatingExpense
from app.models.organization import Organization
from app.schemas.common import Message
from app.schemas.expenses import ExpenseCreate, ExpenseListOut, ExpenseOut, ExpenseVoid
from app.services import idempotency_service
from app.services.audit_service import record_audit

router = APIRouter()


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
        items=rows,
        totals_by_currency={currency: format(amount or Decimal("0.00"), ".2f")
                            for currency, amount in sorted(totals_rows)},
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
