"""Aggregate v1 API router.

One aggregator keeps ``main.py`` clean and makes the full API surface easy to
read. Every domain module is mounted here.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.routes import (
    analytics,
    assistant,
    attendance,
    audit,
    auth,
    campaigns,
    cash,
    celebrations,
    challenges,
    classes,
    companies,
    front_desk,
    industries,
    inbox,
    inbox_channels,
    inbox_webhooks,
    invoices,
    leads,
    initial,
    ladder,
    members,
    memberships,
    notifications,
    nps,
    onboarding,
    organizations,
    payments,
    payroll,
    plans,
    promotions,
    receipts,
    referrals,
    retention,
    saas_billing,
    space,
    staff,
    webhooks,
    winback,
    ws,
)

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(industries.router, tags=["industries"])
api_router.include_router(organizations.router, prefix="/organizations", tags=["organizations"])
api_router.include_router(initial.router, prefix="", tags=["initial"])
api_router.include_router(saas_billing.router, prefix="/saas-billing", tags=["saas-billing"])
api_router.include_router(plans.router, prefix="/plans", tags=["plans"])
api_router.include_router(promotions.router, prefix="/promotions", tags=["promotions"])
api_router.include_router(memberships.router, prefix="/memberships", tags=["memberships"])
api_router.include_router(members.router, prefix="/members", tags=["members"])
api_router.include_router(notifications.router, prefix="/notifications", tags=["notifications"])
api_router.include_router(payments.router, prefix="/payments", tags=["payments"])
api_router.include_router(cash.router, prefix="/cash", tags=["cash"])
api_router.include_router(receipts.router, prefix="/receipts", tags=["receipts"])
api_router.include_router(classes.router, prefix="/classes", tags=["classes"])
api_router.include_router(attendance.router, prefix="/attendance", tags=["attendance"])
api_router.include_router(onboarding.router, prefix="/onboarding", tags=["onboarding"])
api_router.include_router(inbox.router, prefix="/inbox", tags=["inbox"])
api_router.include_router(inbox_channels.router, prefix="/inbox", tags=["inbox-channels"])
api_router.include_router(inbox_webhooks.router, prefix="/inbox", tags=["inbox-webhooks"])
api_router.include_router(front_desk.router, prefix="/front-desk", tags=["front-desk"])
api_router.include_router(staff.router, prefix="/staff", tags=["staff"])
api_router.include_router(payroll.router, prefix="/payroll", tags=["payroll"])
api_router.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
api_router.include_router(retention.router, prefix="/retention", tags=["retention"])
api_router.include_router(ladder.router, prefix="/inactivity-ladder", tags=["inactivity-ladder"])
api_router.include_router(celebrations.router, prefix="/celebrations", tags=["celebrations"])
api_router.include_router(winback.router, prefix="/win-back", tags=["win-back"])
api_router.include_router(nps.router, prefix="/nps", tags=["nps"])
api_router.include_router(challenges.router, prefix="/challenges", tags=["challenges"])
api_router.include_router(campaigns.router, prefix="/campaigns", tags=["campaigns"])
api_router.include_router(assistant.router, prefix="/assistant", tags=["assistant"])
api_router.include_router(audit.router, prefix="/audit", tags=["audit"])
api_router.include_router(webhooks.router, prefix="/webhooks", tags=["webhooks"])
api_router.include_router(ws.router, tags=["realtime"])

# ---- Office vertical (B2B invoicing, seat-holders) ----
api_router.include_router(companies.router, prefix="/companies", tags=["companies"])
api_router.include_router(invoices.router, prefix="/invoices", tags=["invoices"])
api_router.include_router(leads.router, prefix="/leads", tags=["leads"])
api_router.include_router(referrals.router, prefix="/referrals", tags=["referrals"])
api_router.include_router(space.router, prefix="/space", tags=["space"])
