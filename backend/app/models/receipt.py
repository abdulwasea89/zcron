"""ReceiptUpload: payment-proof evidence and staff-review artifacts (Section 10).

Stores the submitted image, extracted text fields, duplicate/cross-validation
signals, staff-review status, and the admin decision trail.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, LargeBinary
from sqlmodel import Field

from app.core.constants import ReceiptStatus
from app.models.base import TimestampModel, UUIDModel


class ReceiptUpload(UUIDModel, TimestampModel, table=True):
    __tablename__ = "receipt_uploads"

    organization_id: str = Field(index=True, foreign_key="organizations.id")
    member_id: str = Field(index=True, foreign_key="organization_members.id")
    plan_id: str | None = Field(default=None, foreign_key="membership_plans.id")

    # Images (Section 10.2)
    original_image_url: str | None = None
    processed_image_url: str | None = None
    image_data: bytes | None = Field(
        default=None,
        sa_column=Column(LargeBinary, nullable=True),
    )
    image_media_type: str | None = Field(default=None, max_length=32)

    # Step 1 OCR (Section 10.3)
    ocr_raw: str | None = None
    extracted_amount: float | None = None
    extracted_date: str | None = None
    extracted_payer: str | None = None
    extracted_payee: str | None = None
    extracted_txn_id: str | None = None
    extracted_method: str | None = None

    # Step 2 authenticity is intentionally not inferred from image content.
    # Keep the nullable legacy column for existing records.
    authenticity_score: float | None = None
    perceptual_hash: str | None = Field(default=None, index=True)
    is_duplicate: bool = False
    cross_validation_json: str | None = None
    flags_json: str | None = None  # suspicious reasons

    # Step 5 confidence + decision (Section 10.4)
    confidence_score: float | None = None
    status: ReceiptStatus = Field(default=ReceiptStatus.UPLOADED, index=True)
    auto_approved: bool = False
    spot_audit_selected: bool = False

    # Admin review trail (Section 10.5 / 10.7)
    reviewed_by: str | None = Field(default=None, foreign_key="users.id")
    review_action: str | None = None
    review_reason: str | None = None
    reviewed_at: datetime | None = None

    payment_id: str | None = Field(default=None, foreign_key="payments.id")
