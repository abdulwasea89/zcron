"""Owner payroll management and staff self-service pay statements (Section 15)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session, require_capability, require_writable_org
from app.core.constants import PayrollStatus
from app.core.permissions import Capability
from app.core.tenancy import TenantContext
from app.schemas.payroll import (
    AdvanceDecision,
    AdvanceOut,
    AdvanceRequest,
    EntryAdjust,
    PayrollEntryOut,
    PayrollRunCreate,
    PayrollRunOut,
    MyPayStatementOut,
    PayoutReconcile,
)
from app.models.membership import OrganizationMember
from app.models.payroll import PayrollEntry, PayrollRun
from sqlmodel import select
from app.services import payroll_service as payroll
from app.services.audit_service import record_audit

router = APIRouter()


@router.get("/me", response_model=list[MyPayStatementOut])
async def my_pay_statements(
    ctx: TenantContext = Depends(require_capability(Capability.CHECK_IN_SHIFT)),
    session: AsyncSession = Depends(get_session),
):
    member = (await session.execute(select(OrganizationMember.id).where(
        OrganizationMember.organization_id == ctx.org_id,
        OrganizationMember.user_id == ctx.user_id,
    ))).scalar_one_or_none()
    if member is None:
        return []
    rows = (await session.execute(
        select(PayrollRun, PayrollEntry)
        .join(PayrollEntry, PayrollEntry.payroll_run_id == PayrollRun.id)
        .where(
            PayrollRun.organization_id == ctx.org_id,
            PayrollEntry.organization_id == ctx.org_id,
            PayrollEntry.staff_member_id == member,
            PayrollRun.status.in_([PayrollStatus.FINALIZED, PayrollStatus.PAID]),
        )
        .order_by(PayrollRun.period_start.desc())
        .limit(100)
    )).all()
    return [MyPayStatementOut(
        payroll_run_id=run.id, period_start=run.period_start, period_end=run.period_end,
        run_status=run.status.value, paid_at=run.paid_at,
        fixed=entry.fixed, hourly_amount=entry.hourly_amount, hours_worked=entry.hours_worked,
        class_amount=entry.class_amount, classes_taught=entry.classes_taught,
        commission_amount=entry.commission_amount, bonus=entry.bonus,
        deductions=entry.deductions, advance_repayment=entry.advance_repayment,
        net=entry.net, payout_method=entry.payout_method.value,
        entry_paid_at=entry.paid_at, payout_reference=entry.payout_reference,
        paid_amount=entry.paid_amount,
    ) for run, entry in rows]


def _entry_out(e) -> PayrollEntryOut:
    return PayrollEntryOut(
        id=e.id, staff_member_id=e.staff_member_id, fixed=e.fixed, hourly_amount=e.hourly_amount,
        hours_worked=e.hours_worked, class_amount=e.class_amount, classes_taught=e.classes_taught,
        commission_amount=e.commission_amount, bonus=e.bonus, deductions=e.deductions,
        advance_repayment=e.advance_repayment, net=e.net, payout_method=e.payout_method.value,
        paid_at=e.paid_at, payout_reference=e.payout_reference, paid_amount=e.paid_amount,
        pay_stub_url=e.pay_stub_url, notes=e.notes,
    )


async def _run_out(session: AsyncSession, run) -> PayrollRunOut:
    entries = await payroll.list_entries(session, org_id=run.organization_id, run_id=run.id)
    return PayrollRunOut(
        id=run.id, period_start=run.period_start, period_end=run.period_end, status=run.status.value,
        total_gross=run.total_gross, total_deductions=run.total_deductions, total_net=run.total_net,
        entries=[_entry_out(e) for e in entries],
    )


@router.post("/runs", response_model=PayrollRunOut, status_code=201, dependencies=[Depends(require_writable_org)])
async def create_run(
    data: PayrollRunCreate,
    ctx: TenantContext = Depends(require_capability(Capability.RUN_PAYROLL)),
    session: AsyncSession = Depends(get_session),
):
    run = await payroll.create_draft(session, org_id=ctx.org_id, data=data, actor_id=ctx.user_id)
    return await _run_out(session, run)


@router.get("/runs", response_model=list[PayrollRunOut])
async def list_runs(
    ctx: TenantContext = Depends(require_capability(Capability.RUN_PAYROLL)),
    session: AsyncSession = Depends(get_session),
):
    runs = await payroll.list_runs(session, org_id=ctx.org_id)
    if runs:
        await record_audit(
            session, action="payroll.viewed", organization_id=ctx.org_id,
            actor_user_id=ctx.user_id, entity_type="payroll_run",
            metadata={"record_count": len(runs)},
        )
    return [await _run_out(session, r) for r in runs]


@router.patch("/runs/{run_id}/entries/{entry_id}", response_model=PayrollEntryOut, dependencies=[Depends(require_writable_org)])
async def adjust_entry(
    run_id: str,
    entry_id: str,
    data: EntryAdjust,
    ctx: TenantContext = Depends(require_capability(Capability.RUN_PAYROLL)),
    session: AsyncSession = Depends(get_session),
):
    entry = await payroll.adjust_entry(session, org_id=ctx.org_id, run_id=run_id, entry_id=entry_id,
                                       data=data, actor_id=ctx.user_id)
    return _entry_out(entry)


@router.post("/runs/{run_id}/lock", response_model=PayrollRunOut, dependencies=[Depends(require_writable_org)])
async def lock_run(
    run_id: str,
    ctx: TenantContext = Depends(require_capability(Capability.RUN_PAYROLL)),
    session: AsyncSession = Depends(get_session),
):
    run = await payroll.lock(session, org_id=ctx.org_id, run_id=run_id, actor_id=ctx.user_id)
    return await _run_out(session, run)


@router.post("/runs/{run_id}/finalize", response_model=PayrollRunOut, dependencies=[Depends(require_writable_org)])
async def finalize_run(
    run_id: str,
    ctx: TenantContext = Depends(require_capability(Capability.RUN_PAYROLL)),
    session: AsyncSession = Depends(get_session),
):
    run = await payroll.finalize(session, org_id=ctx.org_id, run_id=run_id, actor_id=ctx.user_id)
    return await _run_out(session, run)


@router.post("/runs/{run_id}/pay", response_model=PayrollRunOut, dependencies=[Depends(require_writable_org)])
async def pay_run(
    run_id: str,
    ctx: TenantContext = Depends(require_capability(Capability.RUN_PAYROLL)),
    session: AsyncSession = Depends(get_session),
):
    run = await payroll.mark_paid(session, org_id=ctx.org_id, run_id=run_id, actor_id=ctx.user_id)
    return await _run_out(session, run)


@router.post("/runs/{run_id}/entries/{entry_id}/reconcile", response_model=PayrollRunOut,
             dependencies=[Depends(require_writable_org)])
async def reconcile_payout(
    run_id: str,
    entry_id: str,
    data: PayoutReconcile,
    ctx: TenantContext = Depends(require_capability(Capability.RUN_PAYROLL)),
    session: AsyncSession = Depends(get_session),
):
    run = await payroll.reconcile_entry(
        session, org_id=ctx.org_id, run_id=run_id, entry_id=entry_id,
        actor_id=ctx.user_id, data=data,
    )
    return await _run_out(session, run)


# ----------------------------------------------------------------- advances
@router.post("/advances", response_model=AdvanceOut, status_code=201, dependencies=[Depends(require_writable_org)])
async def request_advance(
    data: AdvanceRequest,
    ctx: TenantContext = Depends(require_capability(Capability.CHECK_IN_SHIFT)),
    session: AsyncSession = Depends(get_session),
):
    advance = await payroll.request_advance(session, org_id=ctx.org_id, user_id=ctx.user_id, data=data)
    return AdvanceOut(id=advance.id, staff_member_id=advance.staff_member_id, amount=advance.amount,
                      status=advance.status.value, repayment_per_period=advance.repayment_per_period,
                      repaid_amount=advance.repaid_amount)


@router.get("/advances", response_model=list[AdvanceOut])
async def list_advances(
    ctx: TenantContext = Depends(require_capability(Capability.RUN_PAYROLL)),
    session: AsyncSession = Depends(get_session),
):
    return [
        AdvanceOut(id=a.id, staff_member_id=a.staff_member_id, amount=a.amount, status=a.status.value,
                   repayment_per_period=a.repayment_per_period, repaid_amount=a.repaid_amount)
        for a in await payroll.list_advances(session, org_id=ctx.org_id)
    ]


@router.post("/advances/{advance_id}/decide", response_model=AdvanceOut, dependencies=[Depends(require_writable_org)])
async def decide_advance(
    advance_id: str,
    data: AdvanceDecision,
    ctx: TenantContext = Depends(require_capability(Capability.RUN_PAYROLL)),
    session: AsyncSession = Depends(get_session),
):
    advance = await payroll.decide_advance(session, org_id=ctx.org_id, advance_id=advance_id,
                                            approve=data.approve,
                                            repayment_per_period=data.repayment_per_period,
                                            actor_id=ctx.user_id)
    return AdvanceOut(id=advance.id, staff_member_id=advance.staff_member_id, amount=advance.amount,
                      status=advance.status.value, repayment_per_period=advance.repayment_per_period,
                      repaid_amount=advance.repaid_amount)
