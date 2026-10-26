"""Receipt evidence extraction and review routing (Section 10.3-10.4).

Runs the five-step pipeline on an uploaded receipt and persists the verdict:

  1. OCR extraction (amount, date, payer, payee, txn id, method)
  2. Do not infer authenticity from a screenshot
  3. Near-duplicate detection (64-bit dHash vs up to 2,000 recent org receipts)
  4. Cross-field validation (amount matches a plan, gym name matches, etc.)
  5. OCR/cross-field signal (0-100) -> staff review queue

All submissions stay in the staff review queue. OCR and duplicate signals help
staff inspect a claim but cannot verify that funds reached the organization.

This module is import-safe and callable inline (the route awaits it) so the full
pipeline runs without a Celery broker. In production it would be a Celery task.
"""

from __future__ import annotations

import json
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer
from sqlmodel import select

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
    """True when 64-bit dHashes differ by at most eight pixels."""

    if a.startswith("sha256:") or b.startswith("sha256:"):
        return a == b
    try:
        return len(a) == 16 and len(b) == 16 and (int(a, 16) ^ int(b, 16)).bit_count() <= 8
    except ValueError:
        return False


async def _find_duplicate(
    session: AsyncSession, *, org_id: str, phash: str, exclude_id: str
) -> ReceiptUpload | None:
    candidates = (
        await session.execute(
            select(ReceiptUpload).options(defer(ReceiptUpload.image_data)).where(
                ReceiptUpload.organization_id == org_id,
                ReceiptUpload.perceptual_hash.is_not(None),
                ReceiptUpload.id != exclude_id,
            ).order_by(ReceiptUpload.created_at.desc()).limit(2000)
        )
    ).scalars()
    for c in candidates:
        if _hashes_match(c.perceptual_hash or "", phash):
            return c
    return None


async def _cross_validate(
    session: AsyncSession, *, org: Organization, receipt: ReceiptUpload, ocr
) -> tuple[dict, list[str]]:
    """Step 4: cross-field validation. Returns the result signals and flags."""

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
    amount_matches_plan = (
        matched_plan is not None
        and ocr.amount is not None
        and abs(float(matched_plan.price) - ocr.amount) < 0.01
    )
    results["amount_matches_plan"] = amount_matches_plan
    if not amount_matches_plan:
        flags.append("amount_no_plan_match")

    # Gym/payee name matches org?
    payee = (ocr.payee or "").strip().lower()
    results["payee_matches_org"] = bool(payee) and (
        payee in org.name.lower() or org.name.lower() in payee
    )
    if payee and not results["payee_matches_org"]:
        flags.append("payee_mismatch")
    elif not payee:
        flags.append("payee_not_detected")

    # Date within claim window?
    within_window = False
    if ocr.date:
        try:
            from datetime import date as _date

            d = _date.fromisoformat(ocr.date[:10])
            within_window = abs((now_utc().date() - d).days) <= CLAIM_WINDOW_DAYS
        except (ValueError, TypeError):
            within_window = False
    results["date_within_window"] = within_window
    if not within_window and ocr.date:
        flags.append("date_out_of_window")

    return results, flags


def _score(*, ocr_signal: float, is_duplicate: bool, cross: dict, flags: list[str]) -> float:
    """Visible-field and cross-check signal in 0-100, never authenticity."""

    if is_duplicate:
        return 0.0
    score = ocr_signal * 100.0
    if not cross.get("amount_matches_plan"):
        score -= 20
    if not cross.get("payee_matches_org"):
        score -= 15
    if not cross.get("date_within_window"):
        score -= 25
    return max(0.0, min(100.0, round(score, 1)))


async def _activate_via_receipt(
    session: AsyncSession, *, org: Organization, receipt: ReceiptUpload,
    plan: MembershipPlan | None, verified_amount: float | None = None,
) -> None:
    """On auto-approve, create payment + subscription and activate the member."""

    member = await session.get(OrganizationMember, receipt.member_id)
    if member is None:
        return
    # OCR text is untrusted member-provided content. For a selected plan, book
    # its authoritative current price; never let the screenshot set the ledger.
    amount = plan.price if plan else (verified_amount or 0.0)
    currency = plan.currency if plan else org.default_currency

    payment = Payment(
        organization_id=org.id,
        member_id=member.id,
        plan_id=plan.id if plan else None,
        kind=PaymentKind.MEMBER_FEE,
        method=(
            PaymentMethod.MOBILE_WALLET
            if receipt.extracted_method == PaymentMethod.MOBILE_WALLET.value
            else PaymentMethod.BANK_TRANSFER
        ),
        status=PaymentStatus.SUCCEEDED,
        amount=amount,
        currency=currency,
        note="Staff approved payment proof; settlement checked externally",
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
    if member.family_billing_mode == "shared_plan":
        member.family_owner_member_id = None  # A purchase replaces coverage, not an independently billed household link.
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
    # Step 1: extract visible text; do not claim image authenticity.
    ocr = await extract_receipt(image_bytes)
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
    cross, flags = await _cross_validate(session, org=org, receipt=receipt, ocr=ocr)
    if receipt.is_duplicate:
        flags.append("duplicate_receipt")
    receipt.cross_validation_json = json.dumps(cross)
    receipt.flags_json = json.dumps(flags)

    # Step 5: confidence + routing.
    ocr_signal = sum(value is not None for value in (ocr.amount, ocr.date, ocr.txn_id)) / 3
    confidence = _score(
        ocr_signal=ocr_signal,
        is_duplicate=receipt.is_duplicate,
        cross=cross,
        flags=flags,
    )
    receipt.confidence_score = confidence

    # Screenshots are not provider-confirmed settlements. Keep all submissions
    # pending until an authorized staff member verifies the receiving account.
    receipt.status = ReceiptStatus.PENDING_REVIEW
    receipt.auto_approved = False
    flags.append("staff_must_confirm_settlement")
    receipt.flags_json = json.dumps(list(dict.fromkeys(flags)))
    from app.core.constants import NotificationKind
    from app.services.notifications_service import notify_org_owners

    await notify_org_owners(
        session, org_id=org.id, category=NotificationKind.RECEIPT_REVIEW,
        title="Receipt needs review",
        body="A payment screenshot was submitted. Verify the transaction in your bank or wallet before approving.",
        data={"receipt_id": receipt.id, "ocr_signal": confidence},
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
        return "Membership active. Staff approved your payment proof."
    return "We received your screenshot. Staff will verify the transfer before activating payment."
