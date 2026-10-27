"""Read tools: live org data for the assistant (ADR 018).

Every tool wraps the same service the dashboard reads, so the assistant and the
UI report identical numbers. None takes an ``org_id``: it comes from
``current_context()`` (Security Rule #1). Docstrings are the model's API docs —
they are written for the model, not the developer.

Tools return JSON strings (see ``_serialize.as_tool_result``), which is what the
tool protocol expects and what avoids an empty ``list`` return becoming invalid
``role:tool`` content.
"""

from __future__ import annotations

from datetime import date

from langchain_core.tools import tool

from app.agent.context import current_context
from app.core.permissions import Capability, role_has
from app.models.organization import Organization
from app.services.audit_service import record_audit
from app.agent.tools._serialize import (
    as_tool_result,
    member_row,
    payment_row,
    payroll_run_row,
    plan_row,
    receipt_row,
    session_row,
)
from app.services import analytics_service
from app.services import attendance_service as attendance
from app.services import cash_service as cash
from app.services import classes_service as classes
from app.services import members_service as members
from app.services import payments_service as payments
from app.services import payroll_service as payroll
from app.services import plans_service as plans
from app.services import receipts_service as receipts
from app.services import space_service as space

_MAX_ROWS = 25


@tool
async def get_headline_metrics() -> str:
    """Today's headline KPIs: active members, check-ins, revenue, pending
    receipts and pending approvals. Use for "how are we doing today"."""

    ctx = current_context()
    return as_tool_result(await analytics_service.headline_metrics(ctx.session, org_id=ctx.org_id))


@tool
async def get_revenue_summary() -> str:
    """Total revenue, revenue split by payment method, and member counts by
    status. Use for revenue and churn questions."""

    ctx = current_context()
    return as_tool_result(await analytics_service.revenue_analytics(ctx.session, org_id=ctx.org_id))


@tool
async def search_members(query: str = "", limit: int = 20) -> str:
    """Find members by name or email. Leave ``query`` empty to list everyone.
    Returns member_id, name, email, role and membership status."""

    ctx = current_context()
    limit = max(1, min(int(limit), _MAX_ROWS))
    rows = await cash.search_members(ctx.session, org_id=ctx.org_id, q=query or None, limit=limit)
    return as_tool_result([member_row(m, u) for m, u in rows])


@tool
async def get_member(member_id: str) -> str:
    """Full profile for one member: status, current plan, recent payments, and
    anything still owed. Use after ``search_members`` to drill in."""

    ctx = current_context()
    detail = await members.member_detail(ctx.session, org_id=ctx.org_id, member_id=member_id)
    member = detail["member"]
    user = detail["user"]
    plan = detail["plan"]
    last_visit = await attendance.last_visit_at(ctx.session, org_id=ctx.org_id, member_id=member_id)
    return as_tool_result(
        {
            **member_row(member, user),
            "plan": plan_row(plan) if plan else None,
            "last_visit_at": last_visit.isoformat() if last_visit else None,
            "recent_payments": [payment_row(p) for p in detail["payments"][:10]],
            "pending_payments": [
                {"kind": p.kind, "label": p.label, "amount": p.amount}
                for p in detail["pending_payments"]
            ],
        }
    )


@tool
async def list_payments(member_id: str = "", limit: int = 20) -> str:
    """Recent payments, newest first. Pass a ``member_id`` to scope to one
    member. Returns amount, method, status and paid date."""

    ctx = current_context()
    limit = max(1, min(int(limit), _MAX_ROWS))
    rows = await payments.list_payments(
        ctx.session, org_id=ctx.org_id, member_id=member_id or None
    )
    return as_tool_result([payment_row(p) for p in rows[:limit]])


@tool
async def list_pending_receipts() -> str:
    """Receipts awaiting admin review (the AI-verification queue). Returns the
    extracted amount, confidence and duplicate flag for each."""

    ctx = current_context()
    rows = await receipts.review_queue(ctx.session, org_id=ctx.org_id)
    return as_tool_result([receipt_row(r) for r in rows[:_MAX_ROWS]])


@tool
async def list_plans() -> str:
    """Every membership plan (any status) with its price and visibility."""

    ctx = current_context()
    rows = await plans.list_plans(ctx.session, org_id=ctx.org_id)
    return as_tool_result([plan_row(p) for p in rows])


@tool
async def list_payroll_runs() -> str:
    """Recent payroll runs with status and totals. Use before any payroll
    action to find the run id."""

    ctx = current_context()
    if not role_has(ctx.role, Capability.RUN_PAYROLL):
        return as_tool_result({"status": "not_permitted", "detail": "Payroll data is available to the gym owner."})
    rows = await payroll.list_runs(ctx.session, org_id=ctx.org_id)
    await record_audit(ctx.session, action="privacy.data_accessed", organization_id=ctx.org_id,
                       actor_user_id=ctx.user_id, entity_type="payroll",
                       metadata={"source": "assistant", "tool": "list_payroll_runs", "role": ctx.role.value})
    return as_tool_result([payroll_run_row(r) for r in rows[:_MAX_ROWS]])


@tool
async def list_class_sessions() -> str:
    """Scheduled class sessions with capacity and how many seats are booked."""

    ctx = current_context()
    rows = await classes.list_sessions(ctx.session, org_id=ctx.org_id)
    return as_tool_result([session_row(s) for s in rows[:_MAX_ROWS]])


@tool
async def list_space_slots() -> str:
    """Bookable desks and meeting rooms (office vertical), with capacity."""

    ctx = current_context()
    rows = await space.list_slots(ctx.session, org_id=ctx.org_id)
    return as_tool_result([session_row(s) for s in rows[:_MAX_ROWS]])


@tool
async def get_cash_status(business_date: str = "") -> str:
    """Today's logged cash total for reconciliation. Pass ``business_date`` as
    ISO ``YYYY-MM-DD`` to check another day."""

    ctx = current_context()
    org = await ctx.session.get(Organization, ctx.org_id)
    if org is None:
        return as_tool_result({"error": "Workspace not found."})
    day = date.fromisoformat(business_date) if business_date else attendance._local_today(org.timezone)
    total = await cash._system_cash_total(ctx.session, org_id=ctx.org_id, business_date=day)
    return as_tool_result({"business_date": day.isoformat(), "currency": org.default_currency, "cash_total": total})


@tool
async def get_attendance_summary() -> str:
    """Today's gym check-ins: total visits, unique members, 7-day average and
    how many active members have gone dormant (no visit in 14 days). Use for
    attendance and at-risk-member questions."""

    ctx = current_context()
    return as_tool_result(
        await attendance.summary_for_org(ctx.session, org_id=ctx.org_id)
    )


READ_TOOLS = [
    get_headline_metrics,
    get_revenue_summary,
    get_attendance_summary,
    search_members,
    get_member,
    list_payments,
    list_pending_receipts,
    list_plans,
    list_payroll_runs,
    list_class_sessions,
    list_space_slots,
    get_cash_status,
]
