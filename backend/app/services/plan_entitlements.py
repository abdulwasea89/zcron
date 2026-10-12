"""Snapshot the purchased period and visit credits at activation."""

from __future__ import annotations

from calendar import monthrange
from datetime import datetime, timedelta

from app.core.constants import PlanBillingType
from app.core.security import now_utc
from app.models.plan import MembershipPlan


def subscription_terms(plan: MembershipPlan, *, at: datetime | None = None) -> tuple[datetime | None, int | None]:
    start = at or now_utc()
    if plan.billing_type == PlanBillingType.RECURRING:
        length = plan.cycle_length or 1
        unit = plan.cycle_unit or "month"
        if unit in {"month", "year"}:
            months = length * (12 if unit == "year" else 1)
            month_index = start.year * 12 + start.month - 1 + months
            year, zero_based_month = divmod(month_index, 12)
            month = zero_based_month + 1
            end = start.replace(year=year, month=month, day=min(start.day, monthrange(year, month)[1]))
        else:
            end = start + timedelta(days=length * (7 if unit == "week" else 1))
        return end, plan.included_credits
    if plan.billing_type == PlanBillingType.ONE_TIME_PACK:
        end = start + timedelta(days=plan.validity_days) if plan.validity_days else None
        return end, plan.pack_size
    return None, 1  # A drop-in purchase covers one visit.
