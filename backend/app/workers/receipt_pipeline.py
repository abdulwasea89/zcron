"""AI receipt verification pipeline (Section 10.3-10.4).

Runs the five-step pipeline on an uploaded receipt and persists the verdict:

  1. OCR extraction (amount, date, payer, payee, txn id, method)
  2. Authenticity check (font/edit marks/EXIF — modelled by the OCR stub)
  3. Duplicate detection (perceptual hash vs all prior receipts in the org)
  4. Cross-field validation (amount matches a plan, gym name matches, etc.)
  5. Confidence score (0-100) -> routing decision

Decision thresholds come from settings (default 95 auto-approve, 70 review):
  * >= auto_approve  -> AUTO_APPROVED, membership activated instantly,
                        randomly flagged for a later spot audit.
  * review..auto     -> PENDING_REVIEW (admin queue).
  * < review         -> PENDING_REVIEW, flagged suspicious with reasons.

This module is import-safe and callable inline (the route awaits it) so the full
pipeline runs without a Celery broker. In production it would be a Celery task.
"""

from __future__ import annotations

import json
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.config import settings
from app.core.constants import (
    MemberStatus,
    PaymentKind,
    PaymentMethod,
    PaymentStatus,
    ReceiptStatus,
    SubscriptionStatus,
)
from app.core.security import now_utc
from app.integrations.ocr import extract_receipt
from app.models.membership import OrganizationMember
from app.models.organization import Organization
from app.models.payment import Payment
from app.models.plan import MembershipPlan
from app.models.receipt import ReceiptUpload
from app.models.subscription import Subscription
from app.models.user import User
from app.services.audit_service import record_audit

# Claim window: a receipt date must be within this many days of "now".
CLAIM_WINDOW_DAYS = 30


def _hashes_match(a: str, b: str) -> bool:
    """Stub perceptual-hash comparison: exact match on the content hash."""

    return a == b


async def _find_duplicate(
    session: AsyncSession, *, org_id: str, phash: str, exclude_id: str
) -> ReceiptUpload | None:
    candidates = (
        await session.execute(
            select(ReceiptUpload).where(
                ReceiptUpload.organization_id == org_id,
                ReceiptUpload.perceptual_hash == phash,
                ReceiptUpload.id != exclude_id,
            )
        )
    ).scalars()
    for c in candidates:
        if _hashes_match(c.perceptual_hash or "", phash):
            return c
    return None


async def _cross_validate(
    session: AsyncSession, *, org: Organization, receipt: ReceiptUpload, ocr
) -> tuple[dict, list[str], MembershipPlan | None]:
    """Step 4: cross-field validation. Returns (results, flags, matched_plan)."""

    flags: list[str] = list(ocr.flags)
    results: dict = {}

    # Amount matches a known plan?
    matched_plan: MembershipPlan | None = None
    if receipt.plan_id:
        matched_plan = await session.get(MembershipPlan, receipt.plan_id)
    if matched_plan is None and ocr.amount is not None:
        plans = (
            await session.execute(
                select(MembershipPlan).where(MembershipPlan.organization_id == org.id)
            )
        ).scalars()
        for p in plans:
            if abs(p.price - ocr.amount) < 0.01:
                matched_plan = p
                break
    results["amount_matches_plan"] = matched_plan is not None
    if matched_plan is None:
        flags.append("amount_no_plan_match")

    # Gym/payee name matches org?
    payee = (ocr.payee or "").strip().lower()
    results["payee_matches_org"] = bool(payee) and (
        payee in org.name.lower() or org.name.lower() in payee
    )
    if payee and not results["payee_matches_org"]:
        flags.append("payee_mismatch")

    # Date within claim window?
    within_window = True
    if ocr.date:
        try:
            from datetime import date as _date

            d = _date.fromisoformat(ocr.date[:10])
            within_window = abs((now_utc().date() - d).days) <= CLAIM_WINDOW_DAYS
        except (ValueError, TypeError):
            within_window = True  # unparseable -> don't penalise here
    results["date_within_window"] = within_window
    if not within_window:
        flags.append("date_out_of_window")

    return results, flags, matched_plan


def _score(*, authenticity: float, is_duplicate: bool, cross: dict, flags: list[str]) -> float:
    """Step 5: confidence score in 0-100."""

    if is_duplicate:
        return 0.0
    score = authenticity * 100.0
    if not cross.get("amount_matches_plan"):
        score -= 20
    if not cross.get("payee_matches_org"):
        score -= 15
    if not cross.get("date_within_window"):
        score -= 25
    # Each authenticity flag already lowered the OCR score; penalise edit marks more.
    if "possible_edit_marks" in flags:
        score -= 15
    return max(0.0, min(100.0, round(score, 1)))


async def _activate_via_receipt(
    session: AsyncSession, *, org: Organization, receipt: ReceiptUpload,
    plan: MembershipPlan | None,
) -> None:
    """On auto-approve, create payment + subscription and activate the member."""

    member = await session.get(OrganizationMember, receipt.member_id)
    if member is None:
        return
    amount = receipt.extracted_amount or (plan.price if plan else 0.0)
    currency = plan.currency if plan else org.default_currency

    payment = Payment(
        organization_id=org.id,
        member_id=member.id,
        plan_id=plan.id if plan else None,
        kind=PaymentKind.MEMBER_FEE,
        method=PaymentMethod.CASH,  # offline payment proven by receipt
        status=PaymentStatus.SUCCEEDED,
        amount=amount,
        currency=currency,
        note="Activated via AI-verified receipt",
        receipt_id=receipt.id,
        paid_at=now_utc(),
    )
    session.add(payment)
    await session.flush()

    period_end = None
    classes_remaining = None
    if plan is not None:
        from app.services.plan_entitlements import subscription_terms

        period_end, classes_remaining = subscription_terms(plan)
        sub = Subscription(
            organization_id=org.id, member_id=member.id, plan_id=plan.id,
            status=SubscriptionStatus.ACTIVE, price_snapshot=plan.price, currency=plan.currency,
            current_period_end=period_end, classes_remaining=classes_remaining,
            credits_allowance=classes_remaining,
        )
        session.add(sub)
        await session.flush()
        payment.subscription_id = sub.id
        session.add(payment)

    member.member_status = MemberStatus.ACTIVE
    member.family_owner_member_id = None  # a new purchase replaces family coverage
    if member.joined_at is None:
        member.joined_at = now_utc()
    session.add(member)
    from app.services.family_service import sync_family_status

    await sync_family_status(session, org.id, member.id, MemberStatus.ACTIVE)
    from app.services.referrals_service import qualify_referral_for_member

    await qualify_referral_for_member(session, org_id=org.id, member_id=member.id)
    receipt.payment_id = payment.id
    session.add(receipt)


async def process_receipt(
    session: AsyncSession, *, receipt: ReceiptUpload, image_bytes: bytes
) -> ReceiptUpload:
    """Run the full pipeline on a receipt and persist the verdict + routing."""

    org = await session.get(Organization, receipt.organization_id)
    receipt.status = ReceiptStatus.PROCESSING
    session.add(receipt)

    member = await session.get(OrganizationMember, receipt.member_id)
    user = await session.get(User, member.user_id) if member else None
    plan = await session.get(MembershipPlan, receipt.plan_id) if receipt.plan_id else None

    # Step 1-2: OCR + authenticity.
    ocr = await extract_receipt(
        image_bytes,
        expected_amount=plan.price if plan else None,
        expected_payee=org.name if org else None,
        payer_name=user.full_name if user else None,
    )
    receipt.ocr_raw = ocr.raw_text
    receipt.extracted_amount = ocr.amount
    receipt.extracted_date = ocr.date
    receipt.extracted_payer = ocr.payer
    receipt.extracted_payee = ocr.payee
    receipt.extracted_txn_id = ocr.txn_id
    receipt.extracted_method = ocr.method
    receipt.authenticity_score = ocr.authenticity_score
    receipt.perceptual_hash = ocr.perceptual_hash

    # Step 3: duplicate detection.
    dup = await _find_duplicate(session, org_id=org.id, phash=ocr.perceptual_hash, exclude_id=receipt.id)
    receipt.is_duplicate = dup is not None

    # Step 4: cross-field validation.
    cross, flags, matched_plan = await _cross_validate(session, org=org, receipt=receipt, ocr=ocr)
    if receipt.is_duplicate:
        flags.append("duplicate_receipt")
    receipt.cross_validation_json = json.dumps(cross)
    receipt.flags_json = json.dumps(flags)

    # Step 5: confidence + routing.
    confidence = _score(authenticity=ocr.authenticity_score, is_duplicate=receipt.is_duplicate,
                        cross=cross, flags=flags)
    receipt.confidence_score = confidence

    auto = settings.receipt_auto_approve_threshold
    review = settings.receipt_review_threshold
    if confidence >= auto:
        receipt.status = ReceiptStatus.AUTO_APPROVED
        receipt.auto_approved = True
        # Deterministic 5% spot-audit selection (Section 10.5), no RNG needed.
        seed = int((ocr.perceptual_hash or "0")[:8], 16)
        receipt.spot_audit_selected = (seed % 20 == 0)
        await _activate_via_receipt(session, org=org, receipt=receipt,
                                    plan=matched_plan or plan)
        # Let the member know it went through instantly.
        if user is not None:
            from app.core.constants import NotificationKind
            from app.services.notifications_service import create_notification

            await create_notification(
                session, org_id=org.id, recipient_user_id=user.id,
                category=NotificationKind.RECEIPT, title="Receipt approved",
                body="Your payment receipt was approved; your membership is active.",
                data={"receipt_id": receipt.id, "status": ReceiptStatus.AUTO_APPROVED.value},
            )
    else:
        receipt.status = ReceiptStatus.PENDING_REVIEW
        if confidence < review:
            # Below the review floor: flag suspicious with reasons (Section 10.4).
            flags.append("low_confidence")
            receipt.flags_json = json.dumps(flags)
        # Admin needs to look at this one — alert the owners (Sections 10.2/10.4).
        from app.core.constants import NotificationKind
        from app.services.notifications_service import notify_org_owners

        await notify_org_owners(
            session, org_id=org.id, category=NotificationKind.RECEIPT_REVIEW,
            title="Receipt needs review",
            body=f"A receipt needs your review ({round(confidence)}% confidence).",
            data={"receipt_id": receipt.id, "confidence": confidence},
        )

    session.add(receipt)
    await record_audit(session, action="receipt.processed", organization_id=org.id,
                       actor_user_id=user.id if user else None, entity_type="receipt",
                       entity_id=receipt.id,
                       new_values={"confidence": confidence, "status": receipt.status.value,
                                   "auto_approved": receipt.auto_approved,
                                   "duplicate": receipt.is_duplicate})
    return receipt


def member_message(receipt: ReceiptUpload) -> str:
    """The status message shown to the member (Section 10.4)."""

    if receipt.status == ReceiptStatus.AUTO_APPROVED:
        return "Membership active. Your receipt was approved instantly."
    return "Being reviewed. You'll hear back within 24 hours."
