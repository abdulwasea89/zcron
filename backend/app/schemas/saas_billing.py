"""SaaS subscription billing schemas (Section 3)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.core.constants import SaasTier


class TierChangeRequest(BaseModel):
    tier: SaasTier


class BillingPortalOut(BaseModel):
    url: str


class SaasStatusOut(BaseModel):
    saas_tier: str
    saas_status: str
    member_cap: int | None
    current_member_count: int
    current_period_end: datetime | None
    grace_until: datetime | None
    read_only: bool
    retry_count: int = 0
    state_changed_at: datetime | None = None


class InvoiceOut(BaseModel):
    id: str
    amount: float
    currency: str
    status: str
    created_at: datetime
    source: Literal["stripe", "local"] = "local"
    invoice_pdf_url: str | None = None


class InvoicePageOut(BaseModel):
    items: list[InvoiceOut]
    has_more: bool = False


class CancelSubscriptionRequest(BaseModel):
    timing: Literal["now", "period_end"] = "period_end"


class SubscriptionCheckoutConfirm(BaseModel):
    session_id: str
