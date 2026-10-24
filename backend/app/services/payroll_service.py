"""Payroll run lifecycle service (Section 15.2-15.6).

Sequence: draft (auto-generated) -> owner review (adjust bonus/deductions with a
mandatory note) -> lock -> finalize (generate pay stubs, email trainers) -> pay.
Once locked, entries cannot be edited. Advances are requested by staff, approved
by the owner with a repayment schedule, and auto-deducted by the runner engine.

Payroll is owner-only and web-only (Security Rule #7, Section 16).
"""

from __future__ import annotations

from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.constants import AdvanceStatus, PayrollStatus
from app.core.security import now_utc
from app.integrations.email import send_email_safe as send_email
from app.models.membership import OrganizationMember
from app.models.payroll import PayAdvance, PayrollEntry, PayrollRun
from app.models.user import User
from app.schemas.payroll import AdvanceRequest, EntryAdjust, PayrollRunCreate, PayoutReconcile
from app.services.audit_service import record_audit
from app.utils.pdf import render_simple_pdf
from app.workers import payroll_runner

_money = payroll_runner._money


async def _get_run(session: AsyncSession, org_id: str, run_id: str) -> PayrollRun:
    run = await session.get(PayrollRun, run_id)
    if run is None or run.organization_id != org_id:
        raise HTTPException(status_code=404, detail="Payroll run not found.")
    return run


async def _recompute_totals(session: AsyncSession, run: PayrollRun) -> None:
    entries = await list_entries(session, org_id=run.organization_id, run_id=run.id)
    run.total_gross = _money(sum((e.fixed + e.hourly_amount + e.class_amount + e.commission_amount + e.bonus
                                  for e in entries), Decimal("0.00")))
    run.total_deductions = _money(sum((e.deductions + e.advance_repayment for e in entries), Decimal("0.00")))
    run.total_net = _money(sum((e.net for e in entries), Decimal("0.00")))
    session.add(run)


async def create_draft(
    session: AsyncSession, *, org_id: str, data: PayrollRunCreate, actor_id: str
) -> PayrollRun:
    if data.period_end < data.period_start:
        raise HTTPException(status_code=422, detail="period_end before period_start.")
    run = PayrollRun(
        organization_id=org_id, period_start=data.period_start, period_end=data.period_end,
        status=PayrollStatus.DRAFT, created_by=actor_id,
    )
    session.add(run)
    await session.flush()
    entries = await payroll_runner.generate_entries(
        session, org_id=org_id, run_id=run.id,
        period_start=data.period_start, period_end=data.period_end,
    )
    for e in entries:
        e.net = _money(e.fixed + e.hourly_amount + e.class_amount + e.commission_amount
                       + e.bonus - e.deductions - e.advance_repayment)
        session.add(e)
    await _recompute_totals(session, run)
    await record_audit(session, action="payroll.draft_created", organization_id=org_id,
                       actor_user_id=actor_id, entity_type="payroll_run", entity_id=run.id,
                       metadata={"entries": len(entries)})
    return run


async def list_runs(session: AsyncSession, *, org_id: str) -> list[PayrollRun]:
    return list(
        (
            await session.execute(
                select(PayrollRun).where(PayrollRun.organization_id == org_id)
                .order_by(PayrollRun.period_start.desc())
            )
        ).scalars()
    )


async def list_entries(session: AsyncSession, *, org_id: str, run_id: str) -> list[PayrollEntry]:
    return list(
        (
            await session.execute(
                select(PayrollEntry).where(
                    PayrollEntry.organization_id == org_id,
                    PayrollEntry.payroll_run_id == run_id,
                )
            )
        ).scalars()
    )


async def adjust_entry(
    session: AsyncSession, *, org_id: str, run_id: str, entry_id: str, data: EntryAdjust, actor_id: str
) -> PayrollEntry:
    run = await _get_run(session, org_id, run_id)
    if run.status != PayrollStatus.DRAFT:
        raise HTTPException(status_code=409, detail="Payroll is locked; cannot edit.")
    entry = await session.get(PayrollEntry, entry_id)
    if entry is None or entry.payroll_run_id != run_id:
        raise HTTPException(status_code=404, detail="Entry not found.")
    if not data.note.strip():
        raise HTTPException(status_code=422, detail="A note is required for manual changes.")

    old = {"bonus": entry.bonus, "deductions": entry.deductions}
    if data.bonus is not None:
        entry.bonus = data.bonus
    if data.deductions is not None:
        entry.deductions = data.deductions
    if data.payout_method is not None:
        entry.payout_method = data.payout_method
    entry.notes = data.note
    entry.net = _money(entry.fixed + entry.hourly_amount + entry.class_amount + entry.commission_amount
                       + entry.bonus - entry.deductions - entry.advance_repayment)
    session.add(entry)
    await _recompute_totals(session, run)
    await record_audit(session, action="payroll.entry_adjusted", organization_id=org_id,
                       actor_user_id=actor_id, entity_type="payroll_entry", entity_id=entry.id,
                       old_values=old, new_values={"bonus": entry.bonus, "deductions": entry.deductions},
                       metadata={"note": data.note})
    return entry


async def lock(session: AsyncSession, *, org_id: str, run_id: str, actor_id: str) -> PayrollRun:
    run = await _get_run(session, org_id, run_id)
    if run.status != PayrollStatus.DRAFT:
        raise HTTPException(status_code=409, detail="Only a draft can be locked.")
    run.status = PayrollStatus.LOCKED
    run.locked_at = now_utc()
    session.add(run)
    await record_audit(session, action="payroll.locked", organization_id=org_id, actor_user_id=actor_id,
                       entity_type="payroll_run", entity_id=run.id)
    return run


async def finalize(session: AsyncSession, *, org_id: str, run_id: str, actor_id: str) -> PayrollRun:
    """Lock if needed, generate pay stubs, email trainers, mark finalized."""

    run = await _get_run(session, org_id, run_id)
    if run.status not in {PayrollStatus.DRAFT, PayrollStatus.LOCKED}:
        raise HTTPException(status_code=409, detail="Payroll already finalized.")
    if run.status == PayrollStatus.DRAFT:
        run.status = PayrollStatus.LOCKED
        run.locked_at = now_utc()

    entries = await list_entries(session, org_id=org_id, run_id=run_id)
    for entry in entries:
        staff = await session.get(OrganizationMember, entry.staff_member_id)
        user = await session.get(User, staff.user_id) if staff else None
        _pdf = render_simple_pdf(  # stub: would upload to object store
            "Pay Stub",
            [
                f"Period: {run.period_start} to {run.period_end}",
                f"Staff: {user.full_name or user.email if user else entry.staff_member_id}",
                f"Fixed: {entry.fixed:.2f}",
                f"Hourly: {entry.hourly_amount:.2f} ({entry.hours_worked}h)",
                f"Classes: {entry.class_amount:.2f} ({entry.classes_taught})",
                f"Commission: {entry.commission_amount:.2f}",
                f"Bonus: {entry.bonus:.2f}",
                f"Deductions: -{entry.deductions:.2f}",
                f"Advance repayment: -{entry.advance_repayment:.2f}",
                f"NET: {entry.net:.2f}",
                f"Method: {entry.payout_method.value}",
            ],
        )
        entry.pay_stub_url = f"paystubs/{run.id}/{entry.id}.pdf"  # stub object-store key
        session.add(entry)
        # Apply advance repayment now that the run is finalized.
        if entry.advance_repayment > 0:
            advance = await payroll_runner._outstanding_advance(
                session, org_id=org_id, staff_member_id=entry.staff_member_id
            )
            if advance is not None:
                advance.repaid_amount = _money(advance.repaid_amount + entry.advance_repayment)
                if advance.repaid_amount >= advance.amount - Decimal("0.01"):
                    advance.status = AdvanceStatus.REPAID
                session.add(advance)
        if user is not None:
            await send_email(user.email, "Your pay stub",
                             f"Your pay stub for {run.period_start}–{run.period_end} is ready. "
                             f"Net pay: {entry.net:.2f}.")

    run.status = PayrollStatus.FINALIZED
    run.finalized_at = now_utc()
    session.add(run)
    await record_audit(session, action="payroll.finalized", organization_id=org_id, actor_user_id=actor_id,
                       entity_type="payroll_run", entity_id=run.id,
                       metadata={"total_net": run.total_net})
    return run


async def mark_paid(session: AsyncSession, *, org_id: str, run_id: str, actor_id: str) -> PayrollRun:
    raise HTTPException(status_code=409, detail="Record and reconcile each staff payout before the run can be marked paid.")


async def reconcile_entry(
    session: AsyncSession, *, org_id: str, run_id: str, entry_id: str,
    actor_id: str, data: PayoutReconcile,
) -> PayrollRun:
    run = (await session.execute(select(PayrollRun).where(
        PayrollRun.id == run_id, PayrollRun.organization_id == org_id,
    ).with_for_update())).scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="Payroll run not found.")
    if run.status not in {PayrollStatus.FINALIZED, PayrollStatus.PAID}:
        raise HTTPException(status_code=409, detail="Finalize payroll before reconciling payouts.")
    entry = (await session.execute(select(PayrollEntry).where(
        PayrollEntry.id == entry_id,
        PayrollEntry.payroll_run_id == run.id,
        PayrollEntry.organization_id == org_id,
    ).with_for_update())).scalar_one_or_none()
    if entry is None:
        raise HTTPException(status_code=404, detail="Payroll entry not found.")
    if entry.paid_at is not None:
        if entry.payout_reference == data.payout_reference and entry.paid_amount == data.paid_amount:
            return run
        raise HTTPException(status_code=409, detail="This staff payout has already been reconciled.")
    if data.paid_amount != entry.net:
        raise HTTPException(status_code=409, detail=f"Payout amount must match net pay ({entry.net:.2f}).")

    entry.paid_at = now_utc()
    entry.paid_amount = data.paid_amount
    entry.payout_reference = data.payout_reference
    session.add(entry)
    await session.flush()
    entries = list((await session.execute(select(PayrollEntry).where(
        PayrollEntry.payroll_run_id == run.id,
        PayrollEntry.organization_id == org_id,
    ).with_for_update())).scalars())
    if not entries:
        raise HTTPException(status_code=409, detail="Payroll run has no staff payouts to reconcile.")
    if all(item.paid_at is not None for item in entries):
        run.status = PayrollStatus.PAID
        run.paid_at = now_utc()
        session.add(run)
    await record_audit(session, action="payroll.payout_reconciled", organization_id=org_id,
                       actor_user_id=actor_id, entity_type="payroll_entry", entity_id=entry.id,
                       new_values={"paid_amount": entry.paid_amount, "payout_reference": entry.payout_reference})
    return run


# ----------------------------------------------------------------- advances
async def request_advance(
    session: AsyncSession, *, org_id: str, user_id: str, data: AdvanceRequest
) -> PayAdvance:
    member = (
        await session.execute(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == org_id,
                OrganizationMember.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if member is None:
        raise HTTPException(status_code=404, detail="Membership not found.")
    if data.amount <= 0 or data.repayment_per_period <= 0:
        raise HTTPException(status_code=422, detail="Amount and repayment must be positive.")
    advance = PayAdvance(
        organization_id=org_id, staff_member_id=member.id, amount=data.amount,
        status=AdvanceStatus.REQUESTED, repayment_per_period=data.repayment_per_period,
    )
    session.add(advance)
    await session.flush()
    await record_audit(session, action="advance.requested", organization_id=org_id, actor_user_id=user_id,
                       entity_type="pay_advance", entity_id=advance.id)
    return advance


async def decide_advance(
    session: AsyncSession, *, org_id: str, advance_id: str, approve: bool,
    repayment_per_period: Decimal | None, actor_id: str,
) -> PayAdvance:
    advance = await session.get(PayAdvance, advance_id)
    if advance is None or advance.organization_id != org_id:
        raise HTTPException(status_code=404, detail="Advance not found.")
    if advance.status != AdvanceStatus.REQUESTED:
        raise HTTPException(status_code=409, detail="Advance already decided.")
    if approve:
        advance.status = AdvanceStatus.APPROVED
        advance.approved_by = actor_id
        if repayment_per_period is not None:
            advance.repayment_per_period = repayment_per_period
    else:
        advance.status = AdvanceStatus.REJECTED
    session.add(advance)
    await record_audit(session, action=f"advance.{'approved' if approve else 'rejected'}",
                       organization_id=org_id, actor_user_id=actor_id,
                       entity_type="pay_advance", entity_id=advance.id)
    return advance


async def list_advances(session: AsyncSession, *, org_id: str) -> list[PayAdvance]:
    return list(
        (
            await session.execute(
                select(PayAdvance).where(PayAdvance.organization_id == org_id)
            )
        ).scalars()
    )
