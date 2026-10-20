"""Payroll draft generation engine (Section 15.1, 15.3).

Computes each staff member's pay for a period from stackable components:

  fixed monthly salary
  + hourly rate * tracked hours in the period
  + per-class rate * classes they TAUGHT and CHECKED IN for (Section 15.2 gate)
  + commission rate * revenue from members they referred (12-month window)
  - deductions
  - advance repayment (auto-deducted from subsequent payrolls)
  = net

Runnable inline (no Celery broker) so payroll runs in local dev/tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.constants import (
    AdvanceStatus,
    PaymentKind,
    PaymentStatus,
    Role,
    ShiftStatus,
)
from app.models.class_session import ClassSession
from app.models.membership import OrganizationMember
from app.models.payment import Payment
from app.models.payroll import PayAdvance, PayrollEntry
from app.models.staff import Shift

_CENT = Decimal("0.01")


def _money(value: Decimal | float | int) -> Decimal:
    """Round a payroll amount to currency cents using half-up rounding."""
    return Decimal(str(value)).quantize(_CENT, rounding=ROUND_HALF_UP)


@dataclass
class ComputedComponents:
    fixed: Decimal
    hourly_amount: Decimal
    hours_worked: float
    class_amount: Decimal
    classes_taught: int
    commission_amount: Decimal
    advance_repayment: Decimal

    @property
    def gross(self) -> Decimal:
        return _money(self.fixed + self.hourly_amount + self.class_amount + self.commission_amount)


async def _hours_in_period(
    session: AsyncSession, *, staff_member_id: str, start: datetime, end: datetime
) -> float:
    total = (
        await session.execute(
            select(func.coalesce(func.sum(Shift.hours), 0.0)).where(
                Shift.staff_member_id == staff_member_id,
                Shift.status == ShiftStatus.CHECKED_OUT,
                Shift.checked_in_at >= start,
                Shift.checked_in_at <= end,
            )
        )
    ).scalar_one()
    return float(total or 0.0)


async def _classes_taught(
    session: AsyncSession, *, staff_member_id: str, start: datetime, end: datetime
) -> int:
    """Classes the trainer taught AND checked in for (Section 15.2 gate)."""

    count = (
        await session.execute(
            select(func.count()).select_from(ClassSession).where(
                ClassSession.trainer_member_id == staff_member_id,
                ClassSession.trainer_checked_in == True,  # noqa: E712
                ClassSession.cancelled == False,  # noqa: E712
                ClassSession.starts_at >= start,
                ClassSession.starts_at <= end,
            )
        )
    ).scalar_one()
    return int(count or 0)


async def _commission_revenue(
    session: AsyncSession, *, org_id: str, trainer_member_id: str, start: datetime, end: datetime
) -> Decimal:
    """Revenue in the period from members this trainer referred, within the
    12-month attribution window measured from each member's join date
    (Section 18.1: strict 12-month window, no clawbacks)."""

    referred = (
        await session.execute(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == org_id,
                OrganizationMember.referred_by_member_id == trainer_member_id,
            )
        )
    ).scalars()
    total = Decimal("0.00")
    for m in referred:
        if m.joined_at is None:
            continue
        window_end = m.joined_at + timedelta(days=365 * (m.commission_window_months or 12) // 12)
        # Sum member-fee payments in-period and within the member's attribution window.
        payments = (
            await session.execute(
                select(Payment).where(
                    Payment.organization_id == org_id,
                    Payment.member_id == m.id,
                    Payment.kind == PaymentKind.MEMBER_FEE,
                    Payment.status == PaymentStatus.SUCCEEDED,
                    Payment.paid_at >= start,
                    Payment.paid_at <= end,
                )
            )
        ).scalars()
        for p in payments:
            if p.paid_at and p.paid_at <= window_end:
                total += Decimal(str(p.amount))
    return _money(total)


async def _outstanding_advance(
    session: AsyncSession, *, org_id: str, staff_member_id: str
) -> PayAdvance | None:
    return (
        await session.execute(
            select(PayAdvance).where(
                PayAdvance.organization_id == org_id,
                PayAdvance.staff_member_id == staff_member_id,
                PayAdvance.status == AdvanceStatus.APPROVED,
            ).order_by(PayAdvance.created_at)
        )
    ).scalars().first()


async def compute_for_staff(
    session: AsyncSession, *, org_id: str, staff: OrganizationMember,
    period_start: date, period_end: date,
) -> ComputedComponents:
    start = datetime.combine(period_start, time.min)
    end = datetime.combine(period_end, time.max)

    hours = await _hours_in_period(session, staff_member_id=staff.id, start=start, end=end)
    hourly_amount = _money(Decimal(str(hours)) * staff.hourly_rate)
    classes = await _classes_taught(session, staff_member_id=staff.id, start=start, end=end)
    class_amount = _money(Decimal(classes) * staff.per_class_rate)

    commission_amount = Decimal("0.00")
    if staff.commission_rate:
        revenue = await _commission_revenue(session, org_id=org_id, trainer_member_id=staff.id,
                                            start=start, end=end)
        commission_amount = _money(revenue * staff.commission_rate)

    advance = await _outstanding_advance(session, org_id=org_id, staff_member_id=staff.id)
    advance_repayment = Decimal("0.00")
    if advance is not None:
        remaining = advance.amount - advance.repaid_amount
        advance_repayment = _money(min(advance.repayment_per_period, remaining))

    return ComputedComponents(
        fixed=_money(staff.fixed_monthly_salary),
        hourly_amount=hourly_amount,
        hours_worked=round(hours, 2),
        class_amount=class_amount,
        classes_taught=classes,
        commission_amount=commission_amount,
        advance_repayment=advance_repayment,
    )


async def generate_entries(
    session: AsyncSession, *, org_id: str, run_id: str, period_start: date, period_end: date,
) -> list[PayrollEntry]:
    """Create a PayrollEntry for every staff member with any compensation set."""

    staff_members = (
        await session.execute(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == org_id,
                OrganizationMember.role.in_([Role.TRAINER, Role.FRONT_DESK, Role.MANAGER]),
            )
        )
    ).scalars()

    entries: list[PayrollEntry] = []
    for staff in staff_members:
        comp = await compute_for_staff(session, org_id=org_id, staff=staff,
                                       period_start=period_start, period_end=period_end)
        net = _money(comp.gross - comp.advance_repayment)
        # Skip people with zero comp config and zero activity.
        if comp.gross == 0 and comp.advance_repayment == 0:
            continue
        entry = PayrollEntry(
            organization_id=org_id, payroll_run_id=run_id, staff_member_id=staff.id,
            fixed=comp.fixed, hourly_amount=comp.hourly_amount, hours_worked=comp.hours_worked,
            class_amount=comp.class_amount, classes_taught=comp.classes_taught,
            commission_amount=comp.commission_amount, advance_repayment=comp.advance_repayment,
            net=net,
        )
        session.add(entry)
        entries.append(entry)
    await session.flush()
    return entries
