"""The roster: 5 domains, 40 specialists (ADR 019).

Each entry is a named analyst with a fixed remit. Thirty-two are deterministic —
a single read-only aggregate over the org's tables, exact and effectively free.
The eight marked ``model_backed`` are the ones where the answer is a judgement
(a risk read, a conflict, a quality gap) rather than a number; those gather their
own evidence first and then ask, so the model reasons over real rows rather than
over the question alone.

Two things every specialist obeys:

* It takes no ``org_id``. Tenant scope comes from the ``AgentContext`` the
  orchestrator binds, exactly as the tools do (ADR 018 §3, Security Rule #1).
  Forty specialist prompts is forty chances to be careless, so the roster is
  never given the chance: none of these functions accepts a scope argument.
* It returns a :class:`Finding`. An agent with nothing to look at returns
  ``skipped`` with a reason rather than an empty string, so the UI can show the
  row as accounted-for instead of silently dropping it.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import replace
from datetime import timedelta

from sqlalchemy import func
from sqlmodel import select

from app.agent.context import AgentContext
from app.agent.swarm.queries import (
    count as _count,
    group_count as _group_count,
    group_total as _group_total,
    render_rows as _rows,
    total as _total,
)
from app.agent.swarm.types import (
    STATUS_DONE,
    STATUS_SKIPPED,
    AskFn,
    Domain,
    Finding,
    Specialist,
)
from app.core.constants import (
    IdempotencyStatus,
    MemberStatus,
    PaymentStatus,
    ReceiptStatus,
    STAFF_ROLES,
)
from app.core.industry import MoneyMode, get_industry
from app.core.security import now_utc
from app.models.audit_log import AuditLog
from app.models.attendance import Attendance
from app.models.cash import CashReconciliation
from app.models.class_session import ClassSession
from app.models.company_contract import CompanyContract
from app.models.idempotency_key import IdempotencyKey
from app.models.invoice import Invoice
from app.models.membership import OrganizationMember
from app.models.organization import Organization
from app.models.payment import Payment
from app.models.payroll import PayAdvance, PayrollEntry, PayrollRun
from app.models.plan import MembershipPlan
from app.models.receipt import ReceiptUpload
from app.models.session import AuthSession
from app.models.staff import Shift, Task
from app.models.subscription import Subscription
from app.models.user import User

DOMAINS: list[Domain] = [
    Domain("members", "Members", "Who belongs, who is leaving, who owes"),
    Domain("revenue", "Revenue & billing", "Where the money comes from and where it stalls"),
    Domain("payroll", "Payroll & staff", "What the team costs and what it produces"),
    Domain("operations", "Operations", "Classes, space, tasks and the day itself"),
    Domain("risk", "Risk & compliance", "Fraud, drift and the things that bite later"),
]

DOMAIN_NAMES: dict[str, str] = {d.id: d.name for d in DOMAINS}

# Shared instruction for every judgement specialist: reason only from the rows
# it was handed. Without this, a small model answers the question it wishes it
# had been asked, and the finding stops being evidence.
_ANALYST_RULE = (
    " Reason only from the data you are given; never invent figures or entities. "
    "Three sentences maximum. If the data is too thin to support a conclusion, say "
    "that plainly instead of guessing."
)


# ── findings ────────────────────────────────────────────────────────────────


def _done(agent_id: str, text: str) -> Finding:
    return Finding(agent_id=agent_id, status=STATUS_DONE, summary=text.strip())


def _skip(agent_id: str, why: str) -> Finding:
    return Finding(agent_id=agent_id, status=STATUS_SKIPPED, summary=why)


# ── builders ────────────────────────────────────────────────────────────────


def _is_office(org: Organization | None) -> bool:
    """True for the B2B-invoicing verticals (office, academy, coworking).

    A gym's questions and an office's questions are not the same questions, so
    the specialists that could go either way branch on this rather than
    reporting a gym-shaped zero to an office.
    """

    if org is None:
        return False
    try:
        return get_industry(org.industry or "gym").money == MoneyMode.B2B_INVOICE
    except (KeyError, ValueError):
        return False


def _spec(
    agent_id: str,
    name: str,
    specialization: str,
    why: str,
    run: Callable[[AgentContext], Awaitable[Finding]],
) -> Specialist:
    """A deterministic specialist: one read-only query, one finding."""

    async def wrapper(ctx: AgentContext, ask: AskFn, question: str) -> Finding:  # noqa: ARG001
        return await run(ctx)

    # The domain is filled in by the roster block below, once, from the group
    # each specialist is listed under — so it is stated in one place rather than
    # repeated in forty constructor calls.
    return Specialist(
        id=agent_id,
        name=name,
        domain="",
        specialization=specialization,
        why=why,
        run=wrapper,
    )


def _analyst(
    agent_id: str,
    name: str,
    specialization: str,
    why: str,
    gather: Callable[[AgentContext], Awaitable[tuple[str, str] | None]],
) -> Specialist:
    """A judgement specialist: gather evidence, then ask.

    ``gather`` returns ``(evidence, system_prompt)``, or ``None`` when there is
    nothing worth a model call — which is how a judgement specialist reports
    ``skipped`` without ever spending a token.
    """

    async def wrapper(ctx: AgentContext, ask: AskFn, question: str) -> Finding:
        gathered = await gather(ctx)
        if gathered is None:
            return _skip(agent_id, "Nothing in this org's data for this remit to read.")
        evidence, system = gathered
        answer = await ask(system + _ANALYST_RULE, f"Question: {question}\n\nData: {evidence}")
        if not answer.strip():
            return _skip(agent_id, "The model returned nothing for this remit.")
        # The evidence rides along with the conclusion. A judgement agent's
        # summary is the model's reading of rows it was shown, and a reading is
        # only checkable against what it read — especially here, where eight of
        # forty agents are the only ones whose output is not a raw figure.
        return replace(_done(agent_id, answer), detail=evidence.strip())

    # Same reasoning as _spec: the roster block below assigns the domain.
    return Specialist(
        id=agent_id,
        name=name,
        domain="",
        specialization=specialization,
        why=why,
        run=wrapper,
        model_backed=True,
    )


# ── Members ─────────────────────────────────────────────────────────────────


async def _member_growth(ctx: AgentContext) -> Finding:
    now, session, org = now_utc(), ctx.session, ctx.org_id
    recent = await _count(
        session,
        OrganizationMember,
        OrganizationMember.organization_id == org,
        OrganizationMember.created_at >= now - timedelta(days=30),
    )
    prior = await _count(
        session,
        OrganizationMember,
        OrganizationMember.organization_id == org,
        OrganizationMember.created_at >= now - timedelta(days=60),
        OrganizationMember.created_at < now - timedelta(days=30),
    )
    if recent == 0 and prior == 0:
        return _skip("member_growth", "No members have joined in the last 60 days.")
    delta = recent - prior
    direction = "up" if delta > 0 else "down" if delta < 0 else "flat"
    return _done(
        "member_growth",
        f"{recent} joined in the last 30 days vs {prior} in the 30 before — {direction} by {abs(delta)}.",
    )


async def _member_churn_evidence(ctx: AgentContext) -> tuple[str, str] | None:
    now, session, org = now_utc(), ctx.session, ctx.org_id
    statuses = await _group_count(
        session, OrganizationMember.member_status, OrganizationMember.organization_id == org
    )
    left = await _count(
        session,
        OrganizationMember,
        OrganizationMember.organization_id == org,
        OrganizationMember.member_status == MemberStatus.CANCELLED,
        OrganizationMember.created_at >= now - timedelta(days=90),
    )
    if not statuses:
        return None
    evidence = f"Status split: {_rows(statuses)}. Cancelled in the last 90 days: {left}."

    # The scored model (#34): name the members drifting and the top reason, so
    # the model reasons over a ranked list rather than a raw status count.
    from app.services.retention_service import risk_roster

    risks = await risk_roster(session, org_id=org, min_score=1, limit=5)
    if risks:
        ranked = "; ".join(
            f"{r.name or r.member_id} — {r.score}/100"
            + (f" ({r.reasons[0].label})" if r.reasons else "")
            for r in risks
        )
        evidence += f" Top churn-risk members: {ranked}."

    return evidence, (
        "You are a gym retention analyst. Given the org's membership status split and the "
        "scored churn-risk list, name the churn signals actually present and the segments most "
        "at risk, and say what the single highest-leverage retention action would be."
    )


async def _member_activity(ctx: AgentContext) -> Finding:
    now, session, org = now_utc(), ctx.session, ctx.org_id
    active_attendees = (
        await session.execute(
            select(func.count(func.distinct(Attendance.member_id))).where(
                Attendance.organization_id == org,
                Attendance.checked_in_at >= now - timedelta(days=30),
            )
        )
    ).scalar() or 0
    active = await _count(
        session,
        OrganizationMember,
        OrganizationMember.organization_id == org,
        OrganizationMember.member_status == MemberStatus.ACTIVE,
    )
    if active == 0:
        return _skip("member_activity", "No active members to measure attendance against.")
    pct = round(int(active_attendees) / active * 100, 1)
    return _done(
        "member_activity",
        f"{int(active_attendees)} of {active} active members ({pct}%) checked in within the last "
        f"30 days; {active - int(active_attendees)} have gone dormant.",
    )


async def _member_balances(ctx: AgentContext) -> Finding:
    session, org = ctx.session, ctx.org_id
    owing = await _count(
        session,
        OrganizationMember,
        OrganizationMember.organization_id == org,
        OrganizationMember.member_status.in_([MemberStatus.GRACE, MemberStatus.EXPIRED]),
    )
    open_invoices = await _count(
        session, Invoice, Invoice.organization_id == org, Invoice.status.in_(["sent", "partial"])
    )
    if owing == 0 and open_invoices == 0:
        return _skip("member_balances", "Nobody is carrying a balance.")
    return _done(
        "member_balances",
        f"{owing} members sit in grace or expired (money owed to the gym); {open_invoices} company "
        "invoices are still open.",
    )


async def _member_demographics(ctx: AgentContext) -> Finding:
    session, org = ctx.session, ctx.org_id
    by_city = await _group_count(
        session,
        User.city,
        User.id == OrganizationMember.user_id,
        OrganizationMember.organization_id == org,
        limit=5,
    )
    corporate = await _count(
        session,
        OrganizationMember,
        OrganizationMember.organization_id == org,
        OrganizationMember.company_id.is_not(None),
    )
    individual = await _count(
        session,
        OrganizationMember,
        OrganizationMember.organization_id == org,
        OrganizationMember.company_id.is_(None),
    )
    if corporate == 0 and individual == 0:
        return _skip("member_demographics", "No members to profile yet.")
    cities = _rows(by_city) if by_city else "city not recorded for anyone yet"
    return _done(
        "member_demographics",
        f"{corporate} company-linked vs {individual} individual accounts. Top cities: {cities}.",
    )


async def _member_lifecycle(ctx: AgentContext) -> Finding:
    session, org = ctx.session, ctx.org_id
    rows = await _group_count(
        session, OrganizationMember.member_status, OrganizationMember.organization_id == org
    )
    if not rows:
        return _skip("member_lifecycle", "No memberships on record.")
    return _done("member_lifecycle", _rows(rows))


async def _member_acquisition(ctx: AgentContext) -> Finding:
    session, org = ctx.session, ctx.org_id
    referred = await _count(
        session,
        OrganizationMember,
        OrganizationMember.organization_id == org,
        OrganizationMember.referred_by_member_id.is_not(None),
    )
    total = await _count(session, OrganizationMember, OrganizationMember.organization_id == org)
    if total == 0:
        return _skip("member_acquisition", "No members on record.")
    pct = round(referred / total * 100, 1)
    return _done(
        "member_acquisition",
        f"{referred} of {total} members ({pct}%) joined through a referral; the rest are unattributed.",
    )


async def _member_cohorts(ctx: AgentContext) -> Finding:
    session, org = ctx.session, ctx.org_id
    month = func.strftime("%Y-%m", OrganizationMember.created_at)
    rows = await _group_count(session, month, OrganizationMember.organization_id == org, limit=6)
    if not rows:
        return _skip("member_cohorts", "No join history to build cohorts from.")
    return _done("member_cohorts", "Signups by month (largest first): " + _rows(rows) + ".")


# ── Revenue & billing ───────────────────────────────────────────────────────


async def _rev_trend(ctx: AgentContext) -> Finding:
    session, org = ctx.session, ctx.org_id
    month = func.strftime("%Y-%m", Payment.created_at)
    rows = await _group_total(
        session,
        month,
        Payment.amount,
        Payment.organization_id == org,
        Payment.status == PaymentStatus.SUCCEEDED,
        limit=6,
    )
    if not rows:
        return _skip("rev_trend", "No successful payments on record.")
    return _done("rev_trend", "Collected by month (largest first): " + _rows(rows) + ".")


async def _rev_by_plan(ctx: AgentContext) -> Finding:
    session, org = ctx.session, ctx.org_id
    rows = await _group_total(
        session,
        Payment.plan_id,
        Payment.amount,
        Payment.organization_id == org,
        Payment.status == PaymentStatus.SUCCEEDED,
        limit=8,
    )
    if not rows:
        return _skip("rev_by_plan", "No plan-attributed revenue yet.")
    named = (
        await session.execute(
            select(MembershipPlan.id, MembershipPlan.name).where(MembershipPlan.organization_id == org)
        )
    ).all()
    names = {pid: pname for pid, pname in named}
    return _done("rev_by_plan", "Revenue by plan: " + _rows([(names.get(k, k), v) for k, v in rows]) + ".")


async def _rev_by_method(ctx: AgentContext) -> Finding:
    session, org = ctx.session, ctx.org_id
    rows = await _group_total(
        session,
        Payment.method,
        Payment.amount,
        Payment.organization_id == org,
        Payment.status == PaymentStatus.SUCCEEDED,
    )
    if not rows:
        return _skip("rev_by_method", "No successful payments on record.")
    return _done("rev_by_method", "Collected by method: " + _rows(rows) + ".")


async def _collections_evidence(ctx: AgentContext) -> tuple[str, str] | None:
    session, org = ctx.session, ctx.org_id
    today = now_utc().date()
    overdue = await _count(
        session,
        Invoice,
        Invoice.organization_id == org,
        Invoice.status.in_(["sent", "partial"]),
        Invoice.due_date < today,
    )
    outstanding = await _total(
        session, Invoice.total, Invoice.organization_id == org, Invoice.status.in_(["sent", "partial"])
    )
    if overdue == 0 and outstanding == 0:
        return None
    evidence = f"{overdue} invoices past due; total outstanding balance {outstanding}."
    return evidence, (
        "You are a receivables analyst. Judge how serious this collections position is and what "
        "the first action should be. Be concrete about sequencing."
    )


async def _rev_refunds(ctx: AgentContext) -> Finding:
    session, org = ctx.session, ctx.org_id
    refunded = await _total(session, Payment.refunded_amount, Payment.organization_id == org)
    n = await _count(
        session, Payment, Payment.organization_id == org, Payment.refunded_amount > 0
    )
    if n == 0:
        return _skip("refunds", "No refunds have been issued.")
    return _done("refunds", f"{n} payments refunded, {refunded} returned to members.")


async def _rev_subscriptions(ctx: AgentContext) -> Finding:
    now, session, org = now_utc(), ctx.session, ctx.org_id
    active = await _count(
        session,
        Subscription,
        Subscription.organization_id == org,
        Subscription.status == "active",
    )
    expiring = await _count(
        session,
        Subscription,
        Subscription.organization_id == org,
        Subscription.status == "active",
        Subscription.current_period_end.is_not(None),
        Subscription.current_period_end <= now + timedelta(days=7),
    )
    if active == 0:
        return _skip("subscriptions", "No active subscriptions.")
    return _done(
        "subscriptions",
        f"{active} active subscriptions; {expiring} renew within 7 days and are the ones at risk "
        "of silent lapse.",
    )


async def _pricing_evidence(ctx: AgentContext) -> tuple[str, str] | None:
    session, org = ctx.session, ctx.org_id
    plans = (
        await session.execute(
            select(MembershipPlan.name, MembershipPlan.price, MembershipPlan.status).where(
                MembershipPlan.organization_id == org
            )
        )
    ).all()
    if not plans:
        return None
    evidence = "; ".join(f"{n} at {p} ({s})" for n, p, s in plans[:15])
    return evidence, (
        "You are a pricing analyst for a venue business. Point out anything inconsistent, "
        "loss-making, or mispositioned across the plan ladder, and say which plan is doing the "
        "most work for the business."
    )


async def _rev_aging(ctx: AgentContext) -> Finding:
    session, org = ctx.session, ctx.org_id
    today = now_utc().date()
    rows = (
        await session.execute(
            select(Invoice.due_date, Invoice.total).where(
                Invoice.organization_id == org, Invoice.status.in_(["sent", "partial"])
            )
        )
    ).all()
    if not rows:
        return _skip("invoice_aging", "No open invoices to age.")
    aged: dict[str, float] = {"current": 0.0, "1-30 days": 0.0, "31-60 days": 0.0, "60+ days": 0.0}
    for due, amount in rows:
        days = (today - due).days if due else 0
        if days <= 0:
            aged["current"] += float(amount)
        elif days <= 30:
            aged["1-30 days"] += float(amount)
        elif days <= 60:
            aged["31-60 days"] += float(amount)
        else:
            aged["60+ days"] += float(amount)
    return _done(
        "invoice_aging",
        "Open invoice balance by age: " + _rows([(k, round(v, 2)) for k, v in aged.items()]) + ".",
    )


# ── Payroll & staff ─────────────────────────────────────────────────────────


async def _pay_cost(ctx: AgentContext) -> Finding:
    session, org = ctx.session, ctx.org_id
    runs = (
        await session.execute(
            select(PayrollRun.status, PayrollRun.total_net, PayrollRun.period_start)
            .where(PayrollRun.organization_id == org)
            .order_by(PayrollRun.period_start.desc())
            .limit(6)
        )
    ).all()
    if not runs:
        return _skip("payroll_cost", "No payroll runs have been drafted.")
    net = await _total(session, PayrollRun.total_net, PayrollRun.organization_id == org)
    return _done(
        "payroll_cost",
        f"{len(runs)} recent runs totalling {net} net across all history; the latest ({runs[0][2]}) "
        f"was {runs[0][1]} and is {runs[0][0]}.",
    )


async def _pay_ratio(ctx: AgentContext) -> Finding:
    session, org = ctx.session, ctx.org_id
    payroll = await _total(session, PayrollRun.total_net, PayrollRun.organization_id == org)
    revenue = await _total(
        session,
        Payment.amount,
        Payment.organization_id == org,
        Payment.status == PaymentStatus.SUCCEEDED,
    )
    if revenue == 0:
        return _skip("payroll_ratio", "No collected revenue to compare payroll against.")
    pct = round(payroll / revenue * 100, 1)
    read = "a heavy load" if pct > 50 else "within a workable range" if pct > 25 else "light"
    return _done("payroll_ratio", f"Payroll of {payroll} is {pct}% of {revenue} collected — {read}.")


async def _pay_utilisation(ctx: AgentContext) -> Finding:
    session, org = ctx.session, ctx.org_id
    entries, hours, classes = (
        await session.execute(
            select(
                func.count(),
                func.coalesce(func.sum(PayrollEntry.hours_worked), 0.0),
                func.coalesce(func.sum(PayrollEntry.classes_taught), 0),
            ).where(PayrollEntry.organization_id == org)
        )
    ).one()
    entries = int(entries or 0)
    if entries == 0:
        return _skip("payroll_utilisation", "No payroll entries to measure utilisation from.")
    return _done(
        "payroll_utilisation",
        f"{entries} payroll entries covering {round(float(hours or 0), 1)} tracked hours and "
        f"{int(classes or 0)} classes taught ({round(int(classes or 0) / entries, 1)} classes per entry).",
    )


async def _pay_compensation(ctx: AgentContext) -> Finding:
    session, org = ctx.session, ctx.org_id
    staff = (
        await session.execute(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == org,
                OrganizationMember.role.in_([r.value for r in STAFF_ROLES]),
            )
        )
    ).scalars().all()
    if not staff:
        return _skip("payroll_compensation", "No staff on the roster.")
    fixed = sum(1 for s in staff if s.fixed_monthly_salary)
    hourly = sum(1 for s in staff if s.hourly_rate)
    per_class = sum(1 for s in staff if s.per_class_rate)
    return _done(
        "payroll_compensation",
        f"{len(staff)} staff: {fixed} on a fixed salary, {hourly} hourly, {per_class} paid per class. "
        "Components stack, so these overlap.",
    )


async def _pay_advances(ctx: AgentContext) -> Finding:
    session, org = ctx.session, ctx.org_id
    rows = await _group_count(session, PayAdvance.status, PayAdvance.organization_id == org)
    if not rows:
        return _skip("payroll_advances", "No advances have been requested.")
    outstanding = await _total(
        session, PayAdvance.amount, PayAdvance.organization_id == org, PayAdvance.status == "approved"
    )
    return _done(
        "payroll_advances",
        f"Advances by status: {_rows(rows)}. {outstanding} approved and not yet fully repaid.",
    )


async def _pay_attendance(ctx: AgentContext) -> Finding:
    now, session, org = now_utc(), ctx.session, ctx.org_id
    since = now - timedelta(days=30)
    shifts = await _count(
        session, Shift, Shift.organization_id == org, Shift.created_at >= since
    )
    hours = await _total(
        session, Shift.hours, Shift.organization_id == org, Shift.created_at >= since
    )
    open_shifts = await _count(
        session, Shift, Shift.organization_id == org, Shift.checked_out_at.is_(None)
    )
    if shifts == 0:
        return _skip("payroll_attendance", "No staff shifts were logged in the last 30 days.")
    return _done(
        "payroll_attendance",
        f"{shifts} shifts logged in 30 days totalling {hours} hours; {open_shifts} are still open "
        "(never checked out), which corrupts hourly pay downstream.",
    )


async def _pay_commissions(ctx: AgentContext) -> Finding:
    session, org = ctx.session, ctx.org_id
    commissions = await _total(
        session, PayrollEntry.commission_amount, PayrollEntry.organization_id == org
    )
    bonus = await _total(session, PayrollEntry.bonus, PayrollEntry.organization_id == org)
    deductions = await _total(session, PayrollEntry.deductions, PayrollEntry.organization_id == org)
    if commissions == 0 and bonus == 0 and deductions == 0:
        return _skip("payroll_commissions", "No commissions, bonuses or deductions recorded.")
    return _done(
        "payroll_commissions",
        f"Commissions {commissions}, bonuses {bonus}, deductions {deductions} across all payroll entries.",
    )


async def _pay_roster(ctx: AgentContext) -> Finding:
    session, org = ctx.session, ctx.org_id
    rows = await _group_count(session, OrganizationMember.role, OrganizationMember.organization_id == org)
    if not rows:
        return _skip("payroll_roster", "No members on record.")
    return _done("payroll_roster", "Headcount by role: " + _rows(rows) + ".")


# ── Operations ──────────────────────────────────────────────────────────────


async def _ops_class_fill(ctx: AgentContext) -> Finding:
    session, org = ctx.session, ctx.org_id
    sessions, booked, capacity = (
        await session.execute(
            select(
                func.count(),
                func.coalesce(func.sum(ClassSession.booked_count), 0),
                func.coalesce(func.sum(ClassSession.capacity), 0),
            ).where(
                ClassSession.organization_id == org,
                ClassSession.category == "class",
                ClassSession.cancelled.is_(False),
            )
        )
    ).one()
    sessions, booked, capacity = int(sessions or 0), int(booked or 0), int(capacity or 0)
    if sessions == 0 or capacity == 0:
        return _skip("ops_class_fill", "No scheduled classes to measure fill against.")
    return _done(
        "ops_class_fill",
        f"{sessions} scheduled classes are {round(booked / capacity * 100, 1)}% full "
        f"({booked} of {capacity} seats).",
    )


async def _ops_class_demand(ctx: AgentContext) -> Finding:
    session, org = ctx.session, ctx.org_id
    rows = (
        await session.execute(
            select(ClassSession.title, ClassSession.booked_count)
            .where(ClassSession.organization_id == org, ClassSession.category == "class")
            .order_by(ClassSession.booked_count.desc())
            .limit(5)
        )
    ).all()
    if not rows:
        return _skip("ops_class_demand", "No classes scheduled.")
    return _done("ops_class_demand", "Most booked classes: " + _rows([(t, b) for t, b in rows]) + ".")


async def _ops_space_use(ctx: AgentContext) -> Finding:
    session, org = ctx.session, ctx.org_id
    slots, booked, capacity = (
        await session.execute(
            select(
                func.count(),
                func.coalesce(func.sum(ClassSession.booked_count), 0),
                func.coalesce(func.sum(ClassSession.capacity), 0),
            ).where(
                ClassSession.organization_id == org,
                ClassSession.category != "class",
                ClassSession.cancelled.is_(False),
            )
        )
    ).one()
    slots, booked, capacity = int(slots or 0), int(booked or 0), int(capacity or 0)
    if slots == 0 or capacity == 0:
        return _skip("ops_space_use", "No bookable slots or desks to measure occupancy from.")
    return _done(
        "ops_space_use",
        f"{slots} bookable slots are {round(booked / capacity * 100, 1)}% occupied "
        f"({booked} of {capacity} seats).",
    )


async def _conflicts_evidence(ctx: AgentContext) -> tuple[str, str] | None:
    session, org = ctx.session, ctx.org_id
    rows = (
        await session.execute(
            select(
                ClassSession.title,
                ClassSession.starts_at,
                ClassSession.ends_at,
                ClassSession.trainer_member_id,
            )
            .where(ClassSession.organization_id == org, ClassSession.cancelled.is_(False))
            .order_by(ClassSession.starts_at)
            .limit(60)
        )
    ).all()
    if not rows:
        return None
    evidence = "; ".join(
        f"{t} {s:%Y-%m-%d %H:%M}" + (f"-{e:%H:%M}" if e else "") + (f" trainer {tr}" if tr else "")
        for t, s, e, tr in rows
    )
    return evidence, (
        "You are a scheduling analyst. Identify any sessions that overlap such that the same "
        "trainer would need to be in two places, and any accidental-looking gap. If the schedule "
        "is clean, say so in one sentence."
    )


async def _ops_peak(ctx: AgentContext) -> Finding:
    session, org = ctx.session, ctx.org_id
    hour = func.strftime("%H", ClassSession.starts_at)
    rows = await _group_count(session, hour, ClassSession.organization_id == org, limit=6)
    if not rows:
        return _skip("ops_peak_hours", "No sessions scheduled to profile by hour.")
    return _done("ops_peak_hours", "Busiest hours of day (by session count): " + _rows(rows) + ".")


async def _ops_tasks(ctx: AgentContext) -> Finding:
    now, session, org = now_utc(), ctx.session, ctx.org_id
    open_n = await _count(session, Task, Task.organization_id == org, Task.done.is_(False))
    overdue = await _count(
        session,
        Task,
        Task.organization_id == org,
        Task.done.is_(False),
        Task.deadline.is_not(None),
        Task.deadline < now,
    )
    done = await _count(session, Task, Task.organization_id == org, Task.done.is_(True))
    if open_n == 0 and done == 0:
        return _skip("ops_tasks", "No tasks have been created.")
    return _done("ops_tasks", f"{open_n} tasks open ({overdue} past deadline), {done} completed.")


async def _ops_approvals(ctx: AgentContext) -> Finding:
    session, org = ctx.session, ctx.org_id
    receipts = await _count(
        session,
        ReceiptUpload,
        ReceiptUpload.organization_id == org,
        ReceiptUpload.status == ReceiptStatus.PENDING_REVIEW,
    )
    pending_members = await _count(
        session,
        OrganizationMember,
        OrganizationMember.organization_id == org,
        OrganizationMember.member_status == MemberStatus.PENDING_APPROVAL,
    )
    if receipts == 0 and pending_members == 0:
        return _skip("ops_approvals", "The approval queue is empty.")
    return _done(
        "ops_approvals",
        f"{receipts} receipts and {pending_members} member applications are waiting on a decision.",
    )


async def _ops_office_status(ctx: AgentContext) -> Finding:
    session, org_id = ctx.session, ctx.org_id
    org = await session.get(Organization, org_id)
    if org is None:
        return _skip("ops_office_status", "Organization not found.")
    if not _is_office(org):
        return _skip(
            "ops_office_status",
            f"This is a {org.industry} org, not a seat-based workplace, so seat occupancy does not apply.",
        )
    contracts = (
        await session.execute(
            select(CompanyContract).where(
                CompanyContract.organization_id == org_id, CompanyContract.status == "active"
            )
        )
    ).scalars().all()
    seats = sum(int(c.seats) for c in contracts)
    held = await _count(
        session,
        OrganizationMember,
        OrganizationMember.organization_id == org_id,
        OrganizationMember.member_status == MemberStatus.ACTIVE,
        OrganizationMember.company_id.is_not(None),
    )
    return _done(
        "ops_office_status",
        f"Venue status is '{org.gym_status}'; {held} of {seats} contracted seats are occupied "
        f"across {len(contracts)} active contracts.",
    )


# ── Risk & compliance ───────────────────────────────────────────────────────


async def _receipt_fraud_evidence(ctx: AgentContext) -> tuple[str, str] | None:
    session, org = ctx.session, ctx.org_id
    flagged = (
        await session.execute(
            select(
                ReceiptUpload.extracted_amount,
                ReceiptUpload.confidence_score,
                ReceiptUpload.is_duplicate,
                ReceiptUpload.authenticity_score,
            )
            .where(
                ReceiptUpload.organization_id == org,
                ReceiptUpload.status.in_(
                    [ReceiptStatus.PENDING_REVIEW, ReceiptStatus.REJECTED, ReceiptStatus.REVERSED]
                ),
            )
            .order_by(ReceiptUpload.created_at.desc())
            .limit(25)
        )
    ).all()
    if not flagged:
        return None
    evidence = "; ".join(
        f"amount {a} confidence {c} duplicate={d} authenticity {s}" for a, c, d, s in flagged
    )
    return evidence, (
        "You are a fraud analyst reviewing flagged payment receipts. Judge whether these look "
        "like genuine mistakes, duplicated submissions, or fabrication, and name the common thread. "
        "Reason only from the fields given."
    )


async def _cash_recon(ctx: AgentContext) -> Finding:
    session, org = ctx.session, ctx.org_id
    total = await _count(
        session, CashReconciliation, CashReconciliation.organization_id == org
    )
    off = await _count(
        session,
        CashReconciliation,
        CashReconciliation.organization_id == org,
        CashReconciliation.discrepancy != 0,
    )
    if total == 0:
        return _skip("risk_cash_recon", "No end-of-day cash reconciliation has been run.")
    return _done(
        "risk_cash_recon",
        f"{off} of {total} reconciliations found a discrepancy. Three "
        "discrepancies in 30 days for one staff member triggers an owner alert.",
    )


async def _audit_evidence(ctx: AgentContext) -> tuple[str, str] | None:
    session, org = ctx.session, ctx.org_id
    rows = (
        await session.execute(
            select(AuditLog.action, AuditLog.entity_type, AuditLog.created_at)
            .where(AuditLog.organization_id == org)
            .order_by(AuditLog.created_at.desc())
            .limit(40)
        )
    ).all()
    if not rows:
        return None
    evidence = ", ".join(f"{a} on {e}" for a, e, _ in rows)
    return evidence, (
        "You are an internal-audit analyst. Flag any pattern in these audit actions that looks "
        "unusual, out of hours, or outside what one person should be able to do alone. If nothing "
        "stands out, say so."
    )


async def _duplicate_payments(ctx: AgentContext) -> Finding:
    session, org = ctx.session, ctx.org_id
    dupes = (
        await session.execute(
            select(Payment.member_id, Payment.amount, func.count())
            .where(Payment.organization_id == org, Payment.status == PaymentStatus.SUCCEEDED)
            .group_by(Payment.member_id, Payment.amount)
            .having(func.count() > 1)
            .limit(10)
        )
    ).all()
    if not dupes:
        return _skip(
            "risk_duplicate_payments",
            "No member has been charged the same amount twice — nothing looks double-charged.",
        )
    return _done(
        "risk_duplicate_payments",
        f"{len(dupes)} member/amount pairs were charged more than once: "
        + _rows([(f"{m} at {a}", c) for m, a, c in dupes])
        + ".",
    )


async def _idempotency_evidence(ctx: AgentContext) -> tuple[str, str] | None:
    session, org = ctx.session, ctx.org_id
    stuck = await _count(
        session,
        IdempotencyKey,
        IdempotencyKey.organization_id == org,
        IdempotencyKey.status == IdempotencyStatus.IN_PROGRESS,
    )
    failed = await _count(
        session,
        IdempotencyKey,
        IdempotencyKey.organization_id == org,
        IdempotencyKey.status == IdempotencyStatus.FAILED,
    )
    completed = await _count(
        session,
        IdempotencyKey,
        IdempotencyKey.organization_id == org,
        IdempotencyKey.status == IdempotencyStatus.COMPLETED,
    )
    if stuck == 0 and failed == 0 and completed == 0:
        return None
    evidence = f"{stuck} in progress, {failed} failed, {completed} completed."
    return evidence, (
        "You are a payments reliability analyst. Say what a stuck in-progress idempotency key "
        "implies for money safety, and whether this volume is concerning."
    )


async def _saas_billing(ctx: AgentContext) -> Finding:
    session, org_id = ctx.session, ctx.org_id
    org = await session.get(Organization, org_id)
    if org is None:
        return _skip("risk_saas_billing", "Organization not found.")
    return _done(
        "risk_saas_billing",
        f"Platform subscription is {org.saas_status} on the {org.saas_tier} tier; Stripe Connect is "
        f"'{org.stripe_connect_status}' and consecutive failed-charge retries stand at {org.saas_retry_count}.",
    )


async def _data_quality_evidence(ctx: AgentContext) -> tuple[str, str] | None:
    session, org = ctx.session, ctx.org_id
    total = await _count(session, OrganizationMember, OrganizationMember.organization_id == org)
    if total == 0:
        return None
    incomplete = await _count(
        session,
        OrganizationMember,
        OrganizationMember.organization_id == org,
        OrganizationMember.profile_complete.is_(False),
    )
    no_phone = (
        await session.execute(
            select(func.count())
            .select_from(OrganizationMember)
            .join(User, User.id == OrganizationMember.user_id)
            .where(OrganizationMember.organization_id == org, User.phone.is_(None))
        )
    ).scalar() or 0
    evidence = (
        f"{incomplete} of {total} profiles incomplete; {int(no_phone)} members have no phone number."
    )
    return evidence, (
        "You are a data-quality analyst. Say what this share of incomplete profiles and missing "
        "phone numbers costs a venue operationally, and which to fix first."
    )


async def _security_posture(ctx: AgentContext) -> Finding:
    session, org_id = ctx.session, ctx.org_id
    org = await session.get(Organization, org_id)
    live = await _count(
        session, AuthSession, AuthSession.organization_id == org_id, AuthSession.revoked.is_(False)
    )
    revoked = await _count(
        session, AuthSession, AuthSession.organization_id == org_id, AuthSession.revoked.is_(True)
    )
    mfa = (
        await session.execute(
            select(func.count())
            .select_from(OrganizationMember)
            .join(User, User.id == OrganizationMember.user_id)
            .where(OrganizationMember.organization_id == org_id, User.mfa_enabled.is_(True))
        )
    ).scalar() or 0
    if live == 0 and revoked == 0:
        return _skip("risk_security_posture", "No sessions recorded for this org.")
    required = "required" if org and org.mfa_required else "not required"
    return _done(
        "risk_security_posture",
        f"{live} live sessions ({revoked} revoked); {int(mfa)} accounts have MFA enabled and "
        f"org-wide MFA is {required}.",
    )


# ── the roster ──────────────────────────────────────────────────────────────
#
# Declared as (domain, specialists) pairs so the domain is stated once for the
# block and the builders above can derive it from the id. This is also the list
# the "exactly 5 domains, 40 specialists, ids unique" test reads.

_ROSTER: list[tuple[str, list[Specialist]]] = [
    (
        "members",
        [
            _spec("member_growth", "Member growth", "Net new members, 30 days vs the 30 before", "Growth questions almost always mean a trend, not a total.", _member_growth),
            _analyst("member_churn", "Churn risk", "Which members are drifting toward leaving, and why", "Churn is a judgement about a pattern, not a row count.", _member_churn_evidence),
            _spec("member_activity", "Attendance", "How many active members actually turn up", "Engagement is the leading indicator of churn.", _member_activity),
            _spec("member_balances", "Outstanding balances", "Members in arrears and open invoices", "Receivables age badly and hide in plain sight.", _member_balances),
            _spec("member_demographics", "Member mix", "Cities, corporate vs individual accounts", "Who the venue serves shapes what it should sell.", _member_demographics),
            _spec("member_lifecycle", "Lifecycle split", "Members by status — active, grace, expired, frozen", "The status histogram is the fastest health read there is.", _member_lifecycle),
            _spec("member_acquisition", "Referral attribution", "How much of the base arrived via referral", "Referral share tells you whether word of mouth is working.", _member_acquisition),
            _spec("member_cohorts", "Join cohorts", "Signups bucketed by month", "Cohorts separate a growth problem from a retention problem.", _member_cohorts),
        ],
    ),
    (
        "revenue",
        [
            _spec("rev_trend", "Revenue trend", "Collected revenue by month", "A single total hides the direction of travel.", _rev_trend),
            _spec("rev_by_plan", "Revenue by plan", "Which plans actually earn", "The best-selling plan is not always the best-earning one.", _rev_by_plan),
            _spec("rev_by_method", "Revenue by method", "Card vs cash vs transfer split", "Method mix tells you how much cash handling to reconcile.", _rev_by_method),
            _analyst("collections", "Collections", "Overdue invoices and how serious they are", "An overdue balance is a call to make, not a number to file.", _collections_evidence),
            _spec("refunds", "Refunds", "How much has been given back, on how many payments", "Refund volume is a complaint proxy.", _rev_refunds),
            _spec("subscriptions", "Renewals", "Active subscriptions and those expiring soon", "Lapsing renewals are silent churn.", _rev_subscriptions),
            _analyst("pricing_health", "Pricing health", "Whether the plan ladder is coherent", "Pricing drift is invisible until a margin question is asked.", _pricing_evidence),
            _spec("invoice_aging", "Invoice aging", "Open balances bucketed by how late they are", "Age, not size, predicts whether a receivable is collectable.", _rev_aging),
        ],
    ),
    (
        "payroll",
        [
            _spec("payroll_cost", "Payroll cost", "Total net payroll and the latest run", "What the team costs is the largest controllable line.", _pay_cost),
            _spec("payroll_ratio", "Payroll ratio", "Payroll as a share of collected revenue", "A ratio survives growth; an absolute number does not.", _pay_ratio),
            _spec("payroll_utilisation", "Trainer utilisation", "Hours and classes actually delivered per entry", "Payroll is only expensive if it buys nothing.", _pay_utilisation),
            _spec("payroll_compensation", "Compensation mix", "Fixed vs hourly vs per-class exposure", "Each component carries a different fixed-cost risk.", _pay_compensation),
            _spec("payroll_advances", "Pay advances", "Advances requested, approved and outstanding", "An advance is a debt that payroll must recover.", _pay_advances),
            _spec("payroll_attendance", "Shift attendance", "Shifts logged, hours worked, shifts left open", "Unclosed shifts corrupt every hourly figure downstream.", _pay_attendance),
            _spec("payroll_commissions", "Commissions & deductions", "Referral commissions, bonuses and clawbacks", "Commission is the quietest line on a payroll run.", _pay_commissions),
            _spec("payroll_roster", "Staff roster", "Headcount by role", "Who is on the books frames every staffing question.", _pay_roster),
        ],
    ),
    (
        "operations",
        [
            _spec("ops_class_fill", "Class fill rate", "Booked seats as a share of class capacity", "Empty classes are paid-for time nobody used.", _ops_class_fill),
            _spec("ops_class_demand", "Class demand", "Which sessions fill and which do not", "The timetable should follow demand, not habit.", _ops_class_demand),
            _spec("ops_space_use", "Space occupancy", "Desks, courts and slots actually taken", "Space is the most expensive thing a venue owns.", _ops_space_use),
            _analyst("ops_schedule_conflicts", "Schedule conflicts", "Trainer and room double-bookings", "A clash is invisible until someone turns up to a locked room.", _conflicts_evidence),
            _spec("ops_peak_hours", "Peak hours", "Traffic by hour of day", "Staffing and pricing both follow the peak.", _ops_peak),
            _spec("ops_tasks", "Task throughput", "Open, overdue and completed tasks", "Overdue tasks are work the business already decided to do.", _ops_tasks),
            _spec("ops_approvals", "Approval backlog", "Decisions waiting on a human", "A backlog is the gap between the app and the business.", _ops_approvals),
            _spec("ops_office_status", "Workplace status", "Seat occupancy and open/closed state", "Only meaningful for the seat-based verticals, and says so elsewhere.", _ops_office_status),
        ],
    ),
    (
        "risk",
        [
            _analyst("risk_receipt_fraud", "Receipt fraud", "Whether flagged receipts look fabricated or duplicated", "The point of the receipt pipeline is the calls a human gets wrong.", _receipt_fraud_evidence),
            _spec("risk_cash_recon", "Cash reconciliation", "Discrepancies between counted and logged cash", "Cash is where a small leak goes unnoticed longest.", _cash_recon),
            _analyst("risk_audit_anomalies", "Audit anomalies", "Actions unusual for the role or the hour", "Most misuse is legitimate in isolation and obvious in sequence.", _audit_evidence),
            _spec("risk_duplicate_payments", "Double charges", "Members charged the same amount twice", "The one bug that turns a customer into a complainant.", _duplicate_payments),
            _analyst("risk_idempotency", "Payment reliability", "Stuck and failed idempotency keys", "A stuck key is a payment whose outcome nobody knows.", _idempotency_evidence),
            _spec("risk_saas_billing", "Platform billing", "The org's own SaaS subscription state", "The org losing access is an outage for every member.", _saas_billing),
            _analyst("risk_data_quality", "Data quality", "Gaps in profiles and contact details", "You cannot collect from, or reach, a member with no number.", _data_quality_evidence),
            _spec("risk_security_posture", "Security posture", "Sessions, MFA coverage and revocation", "The cheapest security win is knowing who can still log in.", _security_posture),
        ],
    ),
]

# The block a specialist is listed under is its domain. Applied here, once,
# rather than repeated in forty constructor calls.
SPECIALISTS: list[Specialist] = [
    replace(specialist, domain=domain_id) for domain_id, group in _ROSTER for specialist in group
]

BY_ID: dict[str, Specialist] = {s.id: s for s in SPECIALISTS}

BY_DOMAIN: dict[str, list[Specialist]] = {
    domain.id: [s for s in SPECIALISTS if s.domain == domain.id] for domain in DOMAINS
}


def roster_brief() -> list[dict]:
    """The roster as the planner sees it: id, domain, name, specialization."""

    return [s.as_brief() for s in SPECIALISTS]
