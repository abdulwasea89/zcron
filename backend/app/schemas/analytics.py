"""Analytics schemas (Section 16 web analytics + mobile headline metrics).

Headline metrics are industry-shaped: the org's vertical decides which KPI keys
the service returns (gym keeps today_check_ins / today_revenue / …; office
returns occupied_seats / occupancy_pct / space_mrr / outstanding_invoices). The
fields here are the union, each optional, and the endpoint strips unset keys so
a gym payload stays byte-identical and an office payload carries only office
keys.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class HeadlineMetrics(BaseModel):
    """Industry headline snapshot for dashboards.

    Gym keys are the classic mobile headline set; office/academy add their own.
    Only the current industry's keys are populated (see analytics_service).
    """

    # ---- gym / consumer verticals ----
    today_check_ins: int | None = None
    members_slipping: int | None = None
    today_revenue: float | None = None
    pending_receipts: int | None = None
    pending_approvals: int | None = None
    active_members: int | None = None

    # ---- office vertical ----
    occupied_seats: int | None = None       # active seat-holders bound to a company
    occupancy_pct: float | None = None      # occupied_seats / seats across active contracts
    space_mrr: float | None = None          # Σ seats×price/term (monthly-equivalent) on active contracts
    outstanding_invoices: float | None = None  # unpaid balance on sent/overdue invoices


class CurrencyRevenue(BaseModel):
    total_revenue: str
    revenue_by_method: dict[str, str]


class RevenueAnalytics(BaseModel):
    """Web revenue analytics (Section 16, view_revenue_analytics capability)."""

    total_revenue: float
    revenue_by_method: dict[str, float]
    member_count_by_status: dict[str, int]
    active_members: int
    churn_count: int
    currency: str
    revenue_by_currency: dict[str, CurrencyRevenue] = Field(default_factory=dict)
    operating_expenses_by_currency: dict[str, str] = Field(default_factory=dict)
