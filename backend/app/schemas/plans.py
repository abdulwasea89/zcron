"""Membership plan schemas (Section 6, multi-industry Phase 0)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.core.constants import PlanBillingType, PlanVisibility, TaxMode
from app.core.industry import OfferKind


class PlanCreate(BaseModel):
    name: str
    public_description: str | None = None
    internal_notes: str | None = None
    price: float = Field(default=0.0, ge=0)
    joining_fee: float = Field(default=0.0, ge=0)
    currency: str | None = None  # defaults to org currency
    tax_mode: TaxMode = TaxMode.INCLUSIVE
    tax_rate: float = 0.0
    billing_type: PlanBillingType = PlanBillingType.RECURRING
    cycle_length: int | None = 1
    cycle_unit: str | None = "month"
    auto_renew: bool = True
    trial_days: int = 0
    pack_size: int | None = None
    validity_days: int | None = None
    audience: str = "standard"
    family_capacity: int | None = Field(default=None, ge=2, le=20)
    off_peak_start: str | None = None
    off_peak_end: str | None = None
    included_credits: int | None = Field(default=None, ge=1)
    inclusions_json: str | None = None
    rules_json: str | None = None
    visibility: PlanVisibility = PlanVisibility.PUBLIC
    featured: bool = False
    # Multi-industry offer shape. Defaults to the org's industry offer kind
    # (membership for gym, space for office, course for academy). The industry
    # spec object is validated server-side against the industry JSON Schema.
    offer_kind: OfferKind | None = None
    spec: dict | None = None


class PlanUpdate(BaseModel):
    name: str | None = None
    public_description: str | None = None
    internal_notes: str | None = None
    price: float | None = Field(default=None, ge=0)
    joining_fee: float | None = Field(default=None, ge=0)
    tax_mode: TaxMode | None = None
    tax_rate: float | None = None
    billing_type: PlanBillingType | None = None
    cycle_length: int | None = None
    cycle_unit: str | None = None
    auto_renew: bool | None = None
    trial_days: int | None = None
    pack_size: int | None = None
    validity_days: int | None = None
    audience: str | None = None
    family_capacity: int | None = Field(default=None, ge=2, le=20)
    off_peak_start: str | None = None
    off_peak_end: str | None = None
    included_credits: int | None = Field(default=None, ge=1)
    inclusions_json: str | None = None
    rules_json: str | None = None
    visibility: PlanVisibility | None = None
    featured: bool | None = None
    # Multi-industry offer shape — kept in lockstep with PlanCreate so an edit
    # can change billing type and the vertical spec, not just the core columns.
    offer_kind: OfferKind | None = None
    spec: dict | None = None


class ArchiveRequest(BaseModel):
    replacement_plan_id: str | None = None


class PlanOut(BaseModel):
    id: str
    name: str
    public_description: str | None
    price: float
    joining_fee: float
    currency: str
    tax_mode: str
    tax_rate: float
    billing_type: str
    visibility: str
    status: str
    featured: bool
    cycle_length: int | None = None
    cycle_unit: str | None = None
    pack_size: int | None = None
    validity_days: int | None = None
    audience: str = "standard"
    family_capacity: int | None = None
    off_peak_start: str | None = None
    off_peak_end: str | None = None
    included_credits: int | None = None
    offer_kind: str = "membership"
    spec: dict | None = None
    # AI-written summary, recorded on first view. Null until generated.
    summary: str | None = None
