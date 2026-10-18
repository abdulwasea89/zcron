"""AI receipt verification schemas (Section 10)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ReceiptOut(BaseModel):
    id: str
    member_id: str
    plan_id: str | None
    status: str
    confidence_score: float | None
    auto_approved: bool
    is_duplicate: bool
    extracted_amount: float | None
    extracted_date: str | None
    extracted_payee: str | None
    flags: list[str] = []
    member_message: str


class ReceiptReviewItem(BaseModel):
    id: str
    member_id: str
    plan_id: str | None
    status: str
    confidence_score: float | None
    extracted_amount: float | None
    extracted_date: str | None
    extracted_payer: str | None
    extracted_payee: str | None
    extracted_txn_id: str | None
    extracted_method: str | None
    is_duplicate: bool
    flags: list[str] = []
    original_image_url: str | None


class ReceiptReviewAction(BaseModel):
    action: str  # approve | reject | request_info
    reason: str | None = None
    settlement_confirmed: bool = False
    verified_amount: float | None = Field(default=None, gt=0, le=1_000_000_000)
