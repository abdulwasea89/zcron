"""Receipt upload & admin review service (Section 10.5, 10.7).

Members upload a receipt image (the pipeline runs inline and routes it). Admins
work the review queue: approve / reject / request more info, and can reverse an
auto-approval found bad on audit (member status reverts, member notified).
Every action is audited (Security Rule #10).
"""

from __future__ import annotations

import json
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer
from sqlmodel import select

from app.core.constants import MemberStatus, ReceiptStatus
from app.core.security import now_utc
from app.integrations.email import send_email_safe as send_email
from app.models.membership import OrganizationMember
from app.models.organization import Organization
from app.models.payment import Payment
from app.models.plan import MembershipPlan
from app.models.receipt import ReceiptUpload
from app.models.user import User
from app.realtime import events
from app.services.pricing_service import quote_member_payment
from app.workers import receipt_pipeline


async def _member_for(session: AsyncSession, org_id: str, user_id: str) -> OrganizationMember | None:
    return (
        await session.execute(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == org_id,
                OrganizationMember.user_id == user_id,
            )
        )
    ).scalar_one_or_none()


async def upload_receipt(
    session: AsyncSession, *, org_id: str, user_id: str, image_bytes: bytes,
    plan_id: str | None,
) -> ReceiptUpload:
    """Persist the upload, run the pipeline inline, return the scored receipt."""

    member = await _member_for(session, org_id, user_id)
    if member is None:
        raise HTTPException(status_code=404, detail="Membership not found.")
    if not image_bytes:
        raise HTTPException(status_code=422, detail="Empty image.")
    if len(image_bytes) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Image exceeds 10MB limit.")
    from app.integrations.ocr import validate_image

    try:
        detected_media_type = validate_image(image_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if plan_id is not None:
        plan = await session.get(MembershipPlan, plan_id)
        if plan is None or plan.organization_id != org_id:
            raise HTTPException(status_code=404, detail="Plan not found.")

    receipt = ReceiptUpload(
        organization_id=org_id,
        member_id=member.id,
        plan_id=plan_id,
        image_data=image_bytes,
        image_media_type=detected_media_type,
        processed_image_url=None,
        status=ReceiptStatus.UPLOADED,
    )
    receipt.original_image_url = f"/receipts/{receipt.id}/image"
    session.add(receipt)
    await session.flush()

    await receipt_pipeline.process_receipt(session, receipt=receipt, image_bytes=image_bytes)
    return receipt


def flags_of(receipt: ReceiptUpload) -> list[str]:
    if not receipt.flags_json:
        return []
    try:
        return list(json.loads(receipt.flags_json))
    except (ValueError, TypeError):
        return []


async def review_queue(session: AsyncSession, *, org_id: str) -> list[ReceiptUpload]:
    return list(
        (
            await session.execute(
                select(ReceiptUpload).options(defer(ReceiptUpload.image_data)).where(
                    ReceiptUpload.organization_id == org_id,
                    ReceiptUpload.status == ReceiptStatus.PENDING_REVIEW,
                ).order_by(ReceiptUpload.created_at)
            )
        ).scalars()
    )


async def review(
    session: AsyncSession, *, org_id: str, receipt_id: str, action: str,
    reason: str | None, reviewer_user_id: str, settlement_confirmed: bool = False,
    verified_amount: float | None = None,
) -> ReceiptUpload:
    receipt = await session.get(ReceiptUpload, receipt_id, with_for_update=True, populate_existing=True)
    if receipt is None or receipt.organization_id != org_id:
        raise HTTPException(status_code=404, detail="Receipt not found.")
    if receipt.status not in {ReceiptStatus.PENDING_REVIEW}:
        raise HTTPException(status_code=409, detail="Receipt is not awaiting review.")

    action = action.lower()
    if action == "approve":
        if not settlement_confirmed:
            raise HTTPException(
                status_code=422,
                detail="Confirm that funds settled in the bank or wallet before approving.",
            )
        org = await session.get(Organization, org_id)
        if org is None:
            raise HTTPException(status_code=404, detail="Workspace not found.")
        plan = await session.get(MembershipPlan, receipt.plan_id) if receipt.plan_id else None
        if receipt.plan_id and (plan is None or plan.organization_id != org_id):
            raise HTTPException(status_code=409, detail="The receipt plan is unavailable in this workspace.")
        amount = Decimal(str(verified_amount)) if verified_amount is not None else None
        if amount is None or not amount.is_finite() or amount <= 0 or amount > 1_000_000_000 or amount != amount.quantize(Decimal("0.01")):
            raise HTTPException(
                status_code=422,
                detail="Enter the settled amount in the bank or wallet, with at most two decimal places.",
            )
        quote = await quote_member_payment(session, org_id=org_id, member_id=receipt.member_id, plan=plan) if plan else None
        if quote and amount != Decimal(str(quote.total)):
            raise HTTPException(status_code=422, detail=f"The settled amount must match the current quote: {quote.currency} {quote.total:.2f}.")
        await receipt_pipeline._activate_via_receipt(
            session, org=org, receipt=receipt, plan=plan, verified_amount=float(amount), quote=quote,
        )
        receipt.status = ReceiptStatus.APPROVED
        await _notify(session, receipt, "Receipt approved", "Your payment receipt was approved; "
                      "your membership is active.")
    elif action == "reject":
        receipt.status = ReceiptStatus.REJECTED
        await _notify(session, receipt, "Receipt rejected",
                      f"Your payment receipt was rejected. Reason: {reason or 'not specified'}.")
    elif action == "request_info":
        await _notify(session, receipt, "More info needed",
                      f"We need more information about your receipt. {reason or ''}".strip())
    else:
        raise HTTPException(status_code=422, detail="Invalid action.")

    receipt.review_action = action
    receipt.review_reason = reason
    receipt.reviewed_by = reviewer_user_id
    receipt.reviewed_at = now_utc()
    session.add(receipt)
    from app.services.audit_service import record_audit

    await record_audit(session, action=f"receipt.{action}", organization_id=org_id,
                       actor_user_id=reviewer_user_id, entity_type="receipt", entity_id=receipt.id,
                       metadata={"reason": reason})

    await events.receipt_processed(org_id, receipt_id=receipt.id, status=receipt.status.value)
    return receipt


async def reverse_auto_approval(
    session: AsyncSession, *, org_id: str, receipt_id: str, reviewer_user_id: str, reason: str | None,
) -> ReceiptUpload:
    """Admin reverses an auto-approval found bad on audit (Section 10.5/10.7)."""

    receipt = await session.get(ReceiptUpload, receipt_id, with_for_update=True, populate_existing=True)
    if receipt is None or receipt.organization_id != org_id:
        raise HTTPException(status_code=404, detail="Receipt not found.")
    if not receipt.auto_approved or receipt.status != ReceiptStatus.AUTO_APPROVED:
        raise HTTPException(status_code=409, detail="Receipt was not auto-approved.")

    receipt.status = ReceiptStatus.REVERSED
    receipt.review_action = "reversed"
    receipt.review_reason = reason
    receipt.reviewed_by = reviewer_user_id
    receipt.reviewed_at = now_utc()
    session.add(receipt)

    # Revert member to expired and void the payment.
    member = await session.get(OrganizationMember, receipt.member_id)
    if member is not None:
        member.member_status = MemberStatus.EXPIRED
        session.add(member)
        from app.services.family_service import sync_family_status

        await sync_family_status(session, org_id, member.id, MemberStatus.EXPIRED)
    if receipt.payment_id:
        payment = await session.get(Payment, receipt.payment_id)
        if payment is not None:
            from app.core.constants import PaymentStatus

            payment.status = PaymentStatus.FAILED
            session.add(payment)

    await _notify(session, receipt, "Membership reversed",
                  "A previously approved receipt was reversed on audit. Please resolve payment.")
    from app.services.audit_service import record_audit

    await record_audit(session, action="receipt.reversed", organization_id=org_id,
                       actor_user_id=reviewer_user_id, entity_type="receipt", entity_id=receipt.id,
                       metadata={"reason": reason})
    return receipt


async def _notify(session: AsyncSession, receipt: ReceiptUpload, subject: str, body: str) -> None:
    member = await session.get(OrganizationMember, receipt.member_id)
    if member is None:
        return
    user = await session.get(User, member.user_id)
    if user is not None:
        await send_email(user.email, subject, body)
    # In-app alert mirrors the email (Sections 10.4/10.7).
    from app.core.constants import NotificationKind
    from app.services.notifications_service import create_notification

    await create_notification(
        session, org_id=receipt.organization_id, recipient_user_id=member.user_id,
        category=NotificationKind.RECEIPT, title=subject, body=body,
        data={"receipt_id": receipt.id, "status": receipt.status.value},
    )
