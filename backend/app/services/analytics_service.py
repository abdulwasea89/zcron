"""Analytics aggregations (Section 16).

Headline metrics power the mobile dashboard (today's check-ins, revenue, pending
counts). Full revenue analytics power the web portal (revenue by method, member
status breakdown, churn). All queries are org-scoped (Security Rule #1).
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.constants import MemberStatus, PaymentKind, PaymentStatus, ReceiptStatus
from app.core.industry import MoneyMode, get_industry
from app.core.security import now_utc
from app.models.attendance import Attendance
from app.models.company_contract import CompanyContract
from app.models.invoice import Invoice
from app.models.membership import OrganizationMember
from app.models.organization import Organization
from app.models.operating_expense import OperatingExpense
from app.models.payment import Payment
from app.models.receipt import ReceiptUpload
from app.services.attendance_service import day_bounds

# Monthly-equivalent factor per contract term (for space MRR aggregation).
_TERM_MONTHS = {"monthly": 1, "quarterly": 3, "annual": 12}


def _org_is_office(org: Organization) -> bool:
    try:
        return get_industry(org.industry or "gym").money == MoneyMode.B2B_INVOICE
    except (KeyError, ValueError):
        return False


async def _office_headline(session: AsyncSession, *, org_id: str) -> dict:
    """Headline KPIs for an office vertical (B2B invoicing): seats + invoices.

    occupied_seats = active seat-holders bound to a company. seat capacity = the
    seats across the org's active contracts. space_mrr = seats×price per term,
    normalized to monthly (quarterly /3, annual /12). outstanding_invoices = the
    unpaid balance across sent/partial invoices (overdue is derived, never
    stored).
    """

    occupied_seats = int(
        (
            await session.execute(
                select(func.count()).select_from(OrganizationMember).where(
                    OrganizationMember.organization_id == org_id,
                    OrganizationMember.role == "member",
                    OrganizationMember.member_status == MemberStatus.ACTIVE,
                    OrganizationMember.company_id.is_not(None),
                )
            )
        ).scalar()
        or 0
    )

    contracts = (
        await session.execute(
            select(CompanyContract).where(
                CompanyContract.organization_id == org_id,
                CompanyContract.status == "active",
            )
        )
    ).scalars().all()
    seat_capacity = 0
    space_mrr = 0.0
    for c in contracts:
        seat_capacity += int(c.seats)
        term_total = float(c.seats) * float(c.price_per_seat)
        space_mrr += term_total / _TERM_MONTHS.get(c.term, 1)

    occupancy_pct = round(occupied_seats / seat_capacity * 100, 1) if seat_capacity else 0.0

    # select(Invoice.id) already yields the ids themselves — there is no row
    # object to pull `.id` off. Reading it as one raised on any org with an
    # open invoice, which took the whole headline payload down with it.
    open_ids = (
        await session.execute(
            select(Invoice.id).where(
                Invoice.organization_id == org_id,
                Invoice.status.in_(["sent", "partial"]),
            )
        )
    ).scalars().all()
    outstanding = 0.0
    if open_ids:
        gross = (
            await session.execute(
                select(func.coalesce(func.sum(Invoice.total), 0.0)).where(
                    Invoice.organization_id == org_id,
                    Invoice.status.in_(["sent", "partial"]),
                )
            )
        ).scalar_one()
        paid = (
            await session.execute(
                select(func.coalesce(func.sum(Payment.amount), 0.0)).where(
                    Payment.organization_id == org_id,
                    Payment.status == PaymentStatus.SUCCEEDED,
                    Payment.invoice_id.in_(open_ids),
                )
            )
        ).scalar_one()
        outstanding = round(float(gross or 0.0) - float(paid or 0.0), 2)

    return {
        "occupied_seats": int(occupied_seats),
        "occupancy_pct": float(occupancy_pct),
        "space_mrr": round(space_mrr, 2),
        "outstanding_invoices": outstanding,
    }


async def headline_metrics(session: AsyncSession, *, org_id: str) -> dict:
    org = await session.get(Organization, org_id)
    if org is not None and _org_is_office(org):
        return await _office_headline(session, org_id=org_id)

    today = now_utc().date()
    start = datetime.combine(today, time.min)
    end = datetime.combine(today, time.max)

    # Today's check-ins are *member* visits (the behaviour signal), measured over
    # the org's local day — not staff shift check-ins. Falls back to the UTC day
    # when the org is missing.
    a_start, a_end = day_bounds(org.timezone if org else "UTC")
    check_ins = (
        await session.execute(
            select(func.count(func.distinct(Attendance.member_id))).where(
                Attendance.organization_id == org_id,
                Attendance.checked_in_at >= a_start,
                Attendance.checked_in_at < a_end,
            )
        )
    ).scalar_one()

    slipping = (
        await session.execute(
            select(func.count()).select_from(OrganizationMember).where(
                OrganizationMember.organization_id == org_id,
                OrganizationMember.role == "member",
                OrganizationMember.member_status == MemberStatus.ACTIVE,
                ~select(Attendance.id)
                .where(
                    Attendance.organization_id == org_id,
                    Attendance.member_id == OrganizationMember.id,
                    Attendance.checked_in_at >= now_utc() - timedelta(days=14),
                )
                .exists(),
            )
        )
    ).scalar_one()

    revenue = (
        await session.execute(
            select(func.coalesce(func.sum(Payment.amount), 0.0)).where(
                Payment.organization_id == org_id,
                Payment.status == PaymentStatus.SUCCEEDED,
                Payment.paid_at >= start,
                Payment.paid_at <= end,
            )
        )
    ).scalar_one()

    pending_receipts = (
        await session.execute(
            select(func.count()).select_from(ReceiptUpload).where(
                ReceiptUpload.organization_id == org_id,
                ReceiptUpload.status == ReceiptStatus.PENDING_REVIEW,
            )
        )
    ).scalar_one()

    pending_approvals = (
        await session.execute(
            select(func.count()).select_from(OrganizationMember).where(
                OrganizationMember.organization_id == org_id,
                OrganizationMember.member_status == MemberStatus.PENDING_APPROVAL,
            )
        )
    ).scalar_one()

    active_members = (
        await session.execute(
            select(func.count()).select_from(OrganizationMember).where(
                OrganizationMember.organization_id == org_id,
                OrganizationMember.role == "member",
                OrganizationMember.member_status == MemberStatus.ACTIVE,
            )
        )
    ).scalar_one()

    return {
        "today_check_ins": int(check_ins or 0),
        "members_slipping": int(slipping or 0),
        "today_revenue": float(revenue or 0.0),
        "pending_receipts": int(pending_receipts or 0),
        "pending_approvals": int(pending_approvals or 0),
        "active_members": int(active_members or 0),
    }


async def revenue_analytics(session: AsyncSession, *, org_id: str) -> dict:
    org = await session.get(Organization, org_id)

    payments = (
        await session.execute(
            select(Payment).where(
                Payment.organization_id == org_id,
                Payment.kind.in_([PaymentKind.MEMBER_FEE, PaymentKind.DAY_PASS, PaymentKind.SPACE, PaymentKind.TUITION]),
                Payment.status.in_([PaymentStatus.SUCCEEDED, PaymentStatus.PARTIALLY_REFUNDED]),
            )
        )
    ).scalars()
    totals: dict[str, Decimal] = {}
    methods: dict[str, dict[str, Decimal]] = {}
    for p in payments:
        net = (Decimal(str(p.amount)) - Decimal(str(p.refunded_amount))).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP,
        )
        totals[p.currency] = totals.get(p.currency, Decimal("0")) + net
        by_method = methods.setdefault(p.currency, {})
        by_method[p.method.value] = by_method.get(p.method.value, Decimal("0")) + net
    currency = org.default_currency if org else "USD"
    revenue_by_currency = {
        code: {"total_revenue": format(totals[code], ".2f"),
               "revenue_by_method": {method: format(amount, ".2f") for method, amount in methods[code].items()}}
        for code in sorted(totals)
    }

    members = (
        await session.execute(
            select(OrganizationMember.member_status, func.count())
            .where(OrganizationMember.organization_id == org_id,
                   OrganizationMember.role == "member")
            .group_by(OrganizationMember.member_status)
        )
    ).all()
    by_status: dict[str, int] = {}
    active = 0
    churn = 0
    for status, count in members:
        key = status.value if hasattr(status, "value") else str(status)
        by_status[key] = int(count)
        if status == MemberStatus.ACTIVE:
            active = int(count)
        if status in {MemberStatus.CANCELLED, MemberStatus.EXPIRED}:
            churn += int(count)

    expense_totals = (
        await session.execute(
            select(OperatingExpense.currency, func.sum(OperatingExpense.amount))
            .where(
                OperatingExpense.organization_id == org_id,
                OperatingExpense.voided_at.is_(None),
            )
            .group_by(OperatingExpense.currency)
        )
    ).all()

    return {
        "total_revenue": float(totals.get(currency, 0)),
        "revenue_by_method": {method: float(amount) for method, amount in methods.get(currency, {}).items()},
        "revenue_by_currency": revenue_by_currency,
        "member_count_by_status": by_status,
        "active_members": active,
        "churn_count": churn,
        "currency": currency,
        "operating_expenses_by_currency": {
            currency: format(amount, ".2f") for currency, amount in expense_totals
        },
    }
