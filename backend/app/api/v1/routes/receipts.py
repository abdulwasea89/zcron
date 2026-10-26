"""Payment-proof upload and staff-review API routes (Section 10).

Members upload receipts (multipart); the pipeline runs inline and returns the
verdict + member-facing message. Admins work the review queue.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import undefer
from sqlmodel import select

from app.api.deps import get_session, require_capability
from app.core.permissions import Capability
from app.core.tenancy import TenantContext
from app.models.receipt import ReceiptUpload
from app.models.membership import OrganizationMember
from app.models.user import User
from app.schemas.receipts import ReceiptOut, ReceiptReviewAction, ReceiptReviewItem
from app.services import receipts_service as receipts
from app.workers import receipt_pipeline, spot_audit

router = APIRouter()


def _to_out(r) -> ReceiptOut:
    return ReceiptOut(
        id=r.id, member_id=r.member_id, plan_id=r.plan_id, status=r.status.value,
        confidence_score=r.confidence_score, auto_approved=r.auto_approved,
        is_duplicate=r.is_duplicate, extracted_amount=r.extracted_amount,
        extracted_date=r.extracted_date, extracted_payee=r.extracted_payee,
        flags=receipts.flags_of(r), member_message=receipt_pipeline.member_message(r),
    )


@router.post("/upload", response_model=ReceiptOut, status_code=201)
async def upload_receipt(
    file: UploadFile = File(...),
    plan_id: str | None = Form(default=None),
    ctx: TenantContext = Depends(require_capability(Capability.UPLOAD_RECEIPT)),
    session: AsyncSession = Depends(get_session),
):
    image_bytes = await file.read(10 * 1024 * 1024 + 1)
    receipt = await receipts.upload_receipt(
        session, org_id=ctx.org_id, user_id=ctx.user_id, image_bytes=image_bytes,
        plan_id=plan_id,
    )
    return _to_out(receipt)


@router.get("/review-queue", response_model=list[ReceiptReviewItem])
async def review_queue(
    ctx: TenantContext = Depends(require_capability(Capability.APPROVE_CASH_RECEIPTS)),
    session: AsyncSession = Depends(get_session),
):
    items = await receipts.review_queue(session, org_id=ctx.org_id)
    names = {}
    if items:
        people = (await session.execute(select(
            OrganizationMember.id, OrganizationMember.display_name, User.full_name, User.email,
        ).join(User, User.id == OrganizationMember.user_id).where(
            OrganizationMember.organization_id == ctx.org_id,
            OrganizationMember.id.in_([item.member_id for item in items]),
        ))).all()
        names = {member_id: display_name or full_name or email
                 for member_id, display_name, full_name, email in people}
    return [
        ReceiptReviewItem(
            id=r.id, member_id=r.member_id, member_name=names.get(r.member_id), plan_id=r.plan_id, status=r.status.value,
            confidence_score=r.confidence_score, extracted_amount=r.extracted_amount,
            extracted_date=r.extracted_date, extracted_payer=r.extracted_payer,
            extracted_payee=r.extracted_payee, extracted_txn_id=r.extracted_txn_id,
            extracted_method=r.extracted_method, is_duplicate=r.is_duplicate,
            flags=receipts.flags_of(r), original_image_url=r.original_image_url,
        )
        for r in items
    ]


@router.get("/{receipt_id}/image")
async def receipt_image(
    receipt_id: str,
    ctx: TenantContext = Depends(require_capability(Capability.APPROVE_CASH_RECEIPTS)),
    session: AsyncSession = Depends(get_session),
):
    receipt = (
        await session.execute(
            select(ReceiptUpload)
            .options(undefer(ReceiptUpload.image_data))
            .where(ReceiptUpload.id == receipt_id)
        )
    ).scalar_one_or_none()
    if receipt is None or receipt.organization_id != ctx.org_id or not receipt.image_data:
        raise HTTPException(status_code=404, detail="Receipt image not found.")
    return Response(
        content=receipt.image_data,
        media_type=receipt.image_media_type or "application/octet-stream",
        headers={
            "Cache-Control": "private, no-store",
            "Content-Disposition": "inline",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/{receipt_id}/review", response_model=ReceiptOut)
async def review_receipt(
    receipt_id: str,
    data: ReceiptReviewAction,
    ctx: TenantContext = Depends(require_capability(Capability.APPROVE_CASH_RECEIPTS)),
    session: AsyncSession = Depends(get_session),
):
    receipt = await receipts.review(
        session, org_id=ctx.org_id, receipt_id=receipt_id, action=data.action,
        reason=data.reason, settlement_confirmed=data.settlement_confirmed,
        verified_amount=data.verified_amount,
        reviewer_user_id=ctx.user_id,
    )
    return _to_out(receipt)


@router.post("/{receipt_id}/reverse", response_model=ReceiptOut)
async def reverse_receipt(
    receipt_id: str,
    data: ReceiptReviewAction,
    ctx: TenantContext = Depends(require_capability(Capability.APPROVE_CASH_RECEIPTS)),
    session: AsyncSession = Depends(get_session),
):
    receipt = await receipts.reverse_auto_approval(
        session, org_id=ctx.org_id, receipt_id=receipt_id,
        reviewer_user_id=ctx.user_id, reason=data.reason,
    )
    return _to_out(receipt)


@router.post("/spot-audit/run", response_model=dict)
async def run_spot_audit(
    ctx: TenantContext = Depends(require_capability(Capability.VIEW_REVENUE_ANALYTICS)),
    session: AsyncSession = Depends(get_session),
):
    return await spot_audit.run_spot_audit(session, org_id=ctx.org_id)
