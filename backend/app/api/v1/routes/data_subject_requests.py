"""Owner and manager tools for recording and fulfilling member data requests."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.api.deps import get_session, require_capability
from app.api.deps import get_client_ip
from app.core.constants import Role
from app.core.permissions import Capability
from app.core.security import now_utc
from app.core.tenancy import TenantContext
from app.models.attendance import Attendance
from app.models.class_session import ClassBooking, ClassSession
from app.models.data_subject_request import DataSubjectRequest
from app.models.inbox import InboxConversation, InboxMessage
from app.models.membership import OrganizationMember
from app.models.payment import Payment
from app.models.subscription import Subscription
from app.models.staff import Task
from app.models.user import User
from app.models.trainer_package import TrainerPackage
from app.models.trainer_session import TrainerSessionLog
from app.schemas.privacy import (
    DataSubjectRequestCreate,
    DataSubjectRequestDecision,
    DataSubjectRequestOut,
    MemberMarketingConsentOut,
    MemberMarketingConsentUpdate,
    PrivacyReviewUpdate,
)
from app.services import idempotency_service
from app.services.audit_service import record_audit
from app.services.privacy_service import erase_member_from_workspace

router = APIRouter()


def _consent_out(member: OrganizationMember) -> MemberMarketingConsentOut:
    return MemberMarketingConsentOut(
        member_id=member.id,
        email=member.marketing_email_consent,
        email_updated_at=member.marketing_email_consent_at,
        sms=member.marketing_sms_consent,
        sms_updated_at=member.marketing_sms_consent_at,
        whatsapp=member.marketing_whatsapp_consent,
        whatsapp_updated_at=member.marketing_whatsapp_consent_at,
        in_app=member.marketing_in_app_consent,
        in_app_updated_at=member.marketing_in_app_consent_at,
    )


def _out(request: DataSubjectRequest) -> DataSubjectRequestOut:
    return DataSubjectRequestOut(
        id=request.id, member_id=request.member_id, member_name=request.member_name,
        member_email=request.member_email, request_type=request.request_type, status=request.status,
        note=request.note, resolution_note=request.resolution_note,
        erasure_redacted_at=request.erasure_redacted_at, review_checks=request.review_checks,
        created_at=request.created_at, resolved_at=request.resolved_at,
    )


@router.get("/data-requests", response_model=list[DataSubjectRequestOut])
async def list_data_requests(
    ctx: TenantContext = Depends(require_capability(Capability.VIEW_PRIVATE_MEMBER_PROFILE)),
    session: AsyncSession = Depends(get_session),
):
    rows = await session.execute(
        select(DataSubjectRequest)
        .where(DataSubjectRequest.organization_id == ctx.org_id)
        .order_by(DataSubjectRequest.created_at.desc())
        .limit(200)
    )
    return [_out(row) for row in rows.scalars().all()]


@router.post("/data-requests", response_model=DataSubjectRequestOut, status_code=201)
async def create_data_request(
    data: DataSubjectRequestCreate,
    ctx: TenantContext = Depends(require_capability(Capability.VIEW_PRIVATE_MEMBER_PROFILE)),
    session: AsyncSession = Depends(get_session),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    member = (await session.execute(select(OrganizationMember).where(
        OrganizationMember.id == data.member_id,
        OrganizationMember.organization_id == ctx.org_id,
        OrganizationMember.role == "member",
    ))).scalar_one_or_none()
    if member is None:
        raise HTTPException(status_code=404, detail="Member not found.")
    user = await session.get(User, member.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Member account not found.")
    claim = await idempotency_service.claim(
        session, key=idempotency_key or "", endpoint="privacy.data_request.create",
        body=data.model_dump(), organization_id=ctx.org_id, user_id=ctx.user_id,
    )
    if not claim.claimed:
        return DataSubjectRequestOut.model_validate_json(claim.cached_response or "{}")
    request = DataSubjectRequest(
        organization_id=ctx.org_id, member_id=member.id, request_type=data.request_type,
        member_name=member.display_name or user.full_name or user.email, member_email=user.email,
        note=data.note.strip() if data.note else None, created_by=ctx.user_id,
    )
    session.add(request)
    await session.flush()
    await record_audit(
        session, action="privacy.data_request.created", organization_id=ctx.org_id,
        actor_user_id=ctx.user_id, entity_type="data_subject_request", entity_id=request.id,
        metadata={"request_type": request.request_type, "member_id": member.id},
    )
    result = _out(request)
    await idempotency_service.complete(session, claim.record, code=201, body=result.model_dump_json())
    return result


@router.put("/data-requests/{request_id}/review", response_model=DataSubjectRequestOut)
async def record_privacy_review(
    request_id: str, data: PrivacyReviewUpdate,
    ctx: TenantContext = Depends(require_capability(Capability.VIEW_PRIVATE_MEMBER_PROFILE)),
    session: AsyncSession = Depends(get_session),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    request = (await session.execute(select(DataSubjectRequest).where(
        DataSubjectRequest.id == request_id, DataSubjectRequest.organization_id == ctx.org_id,
    ).with_for_update())).scalar_one_or_none()
    if request is None:
        raise HTTPException(status_code=404, detail="Data request not found.")
    claim = await idempotency_service.claim(session, key=idempotency_key or "",
        endpoint=f"privacy.data_request.review:{request_id}", body=data.model_dump(),
        organization_id=ctx.org_id, user_id=ctx.user_id)
    if not claim.claimed:
        return DataSubjectRequestOut.model_validate_json(claim.cached_response or "{}")
    if request.status in {"completed", "rejected"}:
        raise HTTPException(status_code=409, detail="This request is already closed.")
    request.review_checks = {**request.review_checks, data.item: {
        "outcome": data.outcome, "note": data.note, "reviewed_by": ctx.user_id,
        "reviewed_at": now_utc().isoformat() + "Z",
    }}
    session.add(request)
    await record_audit(session, action="privacy.request_review_recorded", organization_id=ctx.org_id,
        actor_user_id=ctx.user_id, entity_type="data_subject_request", entity_id=request.id,
        metadata={"item": data.item, "outcome": data.outcome})
    result = _out(request)
    await idempotency_service.complete(session, claim.record, code=200, body=result.model_dump_json())
    return result


@router.post("/data-requests/{request_id}/decision", response_model=DataSubjectRequestOut)
async def decide_data_request(
    request_id: str,
    data: DataSubjectRequestDecision,
    ctx: TenantContext = Depends(require_capability(Capability.VIEW_PRIVATE_MEMBER_PROFILE)),
    session: AsyncSession = Depends(get_session),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    request = (await session.execute(select(DataSubjectRequest).where(
        DataSubjectRequest.id == request_id, DataSubjectRequest.organization_id == ctx.org_id,
    ).with_for_update())).scalar_one_or_none()
    if request is None:
        raise HTTPException(status_code=404, detail="Data request not found.")
    claim = await idempotency_service.claim(
        session, key=idempotency_key or "", endpoint=f"privacy.data_request.decision:{request_id}",
        body=data.model_dump(), organization_id=ctx.org_id, user_id=ctx.user_id,
    )
    if not claim.claimed:
        return DataSubjectRequestOut.model_validate_json(claim.cached_response or "{}")
    if request.status in {"completed", "rejected"}:
        raise HTTPException(status_code=409, detail="This request is already closed.")
    if request.request_type == "erasure":
        if data.status in {"in_review", "completed"} and request.review_checks.get("identity", {}).get("outcome") != "verified":
            raise HTTPException(status_code=409, detail="Record verified requester identity and authority before erasure.")
        if data.status == "completed":
            if request.erasure_redacted_at is None:
                raise HTTPException(status_code=409, detail="Begin erasure review and redact the workspace profile before closing this request.")
            if any(request.review_checks.get(item, {}).get("outcome") not in {"verified", "not_applicable"}
                   for item in ("linked_records", "processors", "retention_backups")):
                raise HTTPException(status_code=409, detail="Record linked-record, processor, and retention/backup review before closing erasure.")
    if request.request_type == "erasure" and data.status == "in_review" and request.erasure_redacted_at is None:
        member = (await session.execute(select(OrganizationMember).where(
            OrganizationMember.id == request.member_id,
            OrganizationMember.organization_id == ctx.org_id,
        ))).scalar_one_or_none()
        if member is not None:
            user = await session.get(User, member.user_id)
            if user is None:
                raise HTTPException(status_code=404, detail="Member account not found.")
            await erase_member_from_workspace(
                session, org_id=ctx.org_id, member=member, user=user, actor_id=ctx.user_id,
            )
        request.member_name = "Erased member"
        request.member_email = f"erased-{request.id}@privacy.invalid"
        request.note = None
        request.erasure_redacted_at = now_utc()
        request.resolution_note = "Workspace profile redacted; review linked records, processors, and retention before closing."
    request.status = data.status
    if request.request_type != "erasure" or data.status in {"completed", "rejected"}:
        request.resolution_note = data.resolution_note.strip() if data.resolution_note else None
    request.resolved_at = now_utc() if data.status in {"completed", "rejected"} else None
    request.resolved_by = ctx.user_id if request.resolved_at else None
    session.add(request)
    await record_audit(
        session, action="privacy.data_request.decided", organization_id=ctx.org_id,
        actor_user_id=ctx.user_id, entity_type="data_subject_request", entity_id=request.id,
        new_values={"status": request.status},
    )
    result = _out(request)
    await idempotency_service.complete(session, claim.record, code=200, body=result.model_dump_json())
    return result


@router.get("/members/{member_id}/consent", response_model=MemberMarketingConsentOut)
async def get_member_marketing_consent(
    member_id: str,
    ctx: TenantContext = Depends(require_capability(Capability.MANAGE_MEMBERS)),
    session: AsyncSession = Depends(get_session),
):
    member = (await session.execute(select(OrganizationMember).where(
        OrganizationMember.id == member_id, OrganizationMember.organization_id == ctx.org_id,
        OrganizationMember.role == "member",
    ))).scalar_one_or_none()
    if member is None:
        raise HTTPException(status_code=404, detail="Member not found.")
    return _consent_out(member)


@router.put("/members/{member_id}/consent", response_model=MemberMarketingConsentOut)
async def update_member_marketing_consent(
    member_id: str,
    data: MemberMarketingConsentUpdate,
    ctx: TenantContext = Depends(require_capability(Capability.MANAGE_MEMBERS)),
    session: AsyncSession = Depends(get_session),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    member = (await session.execute(select(OrganizationMember).where(
        OrganizationMember.id == member_id, OrganizationMember.organization_id == ctx.org_id,
        OrganizationMember.role == "member",
    ).with_for_update())).scalar_one_or_none()
    if member is None:
        raise HTTPException(status_code=404, detail="Member not found.")
    claim = await idempotency_service.claim(
        session, key=idempotency_key or "", endpoint=f"privacy.member_consent:{member_id}",
        body=data.model_dump(), organization_id=ctx.org_id, user_id=ctx.user_id,
    )
    if not claim.claimed:
        return MemberMarketingConsentOut.model_validate_json(claim.cached_response or "{}")
    old = {"email": member.marketing_email_consent, "sms": member.marketing_sms_consent,
           "in_app": member.marketing_in_app_consent, "whatsapp": member.marketing_whatsapp_consent}
    now = now_utc()
    if data.whatsapp is not None:
        if member.marketing_whatsapp_consent != data.whatsapp:
            member.marketing_whatsapp_consent_at = now
        member.marketing_whatsapp_consent = data.whatsapp
    if member.marketing_email_consent != data.email:
        member.marketing_email_consent_at = now
    if member.marketing_sms_consent != data.sms:
        member.marketing_sms_consent_at = now
    if member.marketing_in_app_consent != data.in_app:
        member.marketing_in_app_consent_at = now
    member.marketing_email_consent = data.email
    member.marketing_sms_consent = data.sms
    member.marketing_in_app_consent = data.in_app
    session.add(member)
    new = {"email": data.email, "sms": data.sms, "in_app": data.in_app, "whatsapp": member.marketing_whatsapp_consent}
    if old != new:
        await record_audit(
            session, action="privacy.member_marketing_consent_updated", organization_id=ctx.org_id,
            actor_user_id=ctx.user_id, entity_type="member", entity_id=member.id,
            old_values=old, new_values=new,
        )
    result = _consent_out(member)
    await idempotency_service.complete(session, claim.record, code=200, body=result.model_dump_json())
    return result


@router.get("/members/{member_id}/export")
async def export_member_data(
    member_id: str,
    request: Request,
    ctx: TenantContext = Depends(require_capability(Capability.MANAGE_MEMBERS)),
    session: AsyncSession = Depends(get_session),
):
    if ctx.role not in {Role.OWNER, Role.MANAGER}:
        raise HTTPException(status_code=403, detail="Only owners and managers can export member data.")
    member = (await session.execute(select(OrganizationMember).where(
        OrganizationMember.id == member_id, OrganizationMember.organization_id == ctx.org_id,
        OrganizationMember.role == "member",
    ))).scalar_one_or_none()
    if member is None:
        raise HTTPException(status_code=404, detail="Member not found.")
    user = await session.get(User, member.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Member account not found.")
    await record_audit(
        session, action="privacy.member_exported", organization_id=ctx.org_id,
        actor_user_id=ctx.user_id, entity_type="member", entity_id=member.id,
        ip_address=get_client_ip(request), user_agent=request.headers.get("user-agent"),
        metadata={"contains_sensitive_profile_data": True},
    )
    attendance = (await session.execute(select(Attendance).where(
        Attendance.organization_id == ctx.org_id, Attendance.member_id == member.id,
    ).order_by(Attendance.checked_in_at.desc()).limit(5000))).scalars().all()
    class_bookings = (await session.execute(
        select(ClassBooking, ClassSession)
        .join(ClassSession, ClassSession.id == ClassBooking.class_session_id)
        .where(
            ClassBooking.organization_id == ctx.org_id,
            ClassBooking.member_id == member.id,
            ClassSession.organization_id == ctx.org_id,
            ClassSession.category == "class",
        )
        .order_by(ClassSession.starts_at.desc())
        .limit(5000)
    )).all()
    payments = (await session.execute(select(Payment).where(
        Payment.organization_id == ctx.org_id, Payment.member_id == member.id,
    ).order_by(Payment.created_at.desc()).limit(5000))).scalars().all()
    subscriptions = (await session.execute(select(Subscription).where(
        Subscription.organization_id == ctx.org_id, Subscription.member_id == member.id,
    ).order_by(Subscription.created_at.desc()).limit(1000))).scalars().all()
    retention_cases = (await session.execute(select(Task).where(
        Task.organization_id == ctx.org_id, Task.related_member_id == member.id, Task.category == "retention",
    ).order_by(Task.created_at.desc()).limit(5000))).scalars().all()
    training_packages = (await session.execute(select(TrainerPackage).where(
        TrainerPackage.organization_id == ctx.org_id, TrainerPackage.member_id == member.id,
    ).order_by(TrainerPackage.created_at.desc()).limit(5000))).scalars().all()
    training_logs = (await session.execute(select(TrainerSessionLog).where(
        TrainerSessionLog.organization_id == ctx.org_id, TrainerSessionLog.client_member_id == member.id,
    ).order_by(TrainerSessionLog.performed_at.desc()).limit(5000))).scalars().all()
    inbox_messages = (await session.execute(
        select(InboxMessage, InboxConversation.channel)
        .join(InboxConversation, InboxConversation.id == InboxMessage.conversation_id)
        .where(
            InboxMessage.organization_id == ctx.org_id,
            InboxConversation.organization_id == ctx.org_id,
            InboxConversation.member_id == member.id,
        )
        .order_by(InboxMessage.created_at.desc())
        .limit(5000)
    )).all()
    return {
        "account": {
            "email": user.email, "full_name": user.full_name, "phone": user.phone,
            "address": user.address, "city": user.city, "occupation": user.occupation,
            "education": user.education, "date_of_birth": user.date_of_birth,
            "gender": user.gender.value if user.gender else None,
            "emergency_contact": user.emergency_contact,
        },
        "membership": {"id": member.id, "role": member.role.value, "status": member.member_status.value,
                       "family_owner_member_id": member.family_owner_member_id, "family_billing_mode": member.family_billing_mode,
                       "display_name": member.display_name, "phone": member.phone, "joined_at": member.joined_at,
                       "emergency_contact": member.emergency_contact, "goals": member.goals, "tags": member.tags,
                       "health_notes": member.health_notes, "id_document_type": member.id_document_type,
                       "id_document_last4": member.id_document_last4, "photo_url": member.photo_url,
                       "recurring_consent_at": member.recurring_consent_at,
                       "marketing_consent": {
                           "email": member.marketing_email_consent,
                           "email_updated_at": member.marketing_email_consent_at,
                           "sms": member.marketing_sms_consent,
                           "whatsapp": member.marketing_whatsapp_consent,
                           "whatsapp_updated_at": member.marketing_whatsapp_consent_at,
                           "sms_updated_at": member.marketing_sms_consent_at,
                           "in_app": member.marketing_in_app_consent,
                           "in_app_updated_at": member.marketing_in_app_consent_at,
                       }},
        "attendance": [{"checked_in_at": item.checked_in_at, "method": item.method.value,
                        "source": item.source.value, "note": item.note} for item in attendance],
        "class_bookings": [{"status": booking.status.value, "booked_at": booking.created_at,
                            "class_title": class_session.title, "starts_at": class_session.starts_at,
                            "ends_at": class_session.ends_at}
                           for booking, class_session in class_bookings],
        "messages": [{"at": message.created_at, "direction": message.direction.value,
                      "channel": channel.value, "body": message.body,
                      "delivery_status": message.delivery_status}
                     for message, channel in inbox_messages],
        "payments": [{"created_at": item.created_at, "amount": item.amount, "currency": item.currency,
                      "tax_amount": item.tax_amount, "tax_included": item.tax_included,
                      "status": item.status.value, "method": item.method.value, "kind": item.kind.value}
                     for item in payments],
        "subscriptions": [{"created_at": item.created_at, "status": item.status.value,
                           "started_at": item.started_at,
                           "current_period_end": item.current_period_end} for item in subscriptions],
        "retention_cases": [{"created_at": item.created_at, "next_action": item.description,
                             "completed": item.done, "outcome": item.case_outcome} for item in retention_cases],
        "training_packages": [{"name": item.name, "sessions": item.total_sessions,
                               "used_sessions": item.used_sessions, "granted_at": item.granted_at,
                               "expires_at": item.expires_at, "cancelled_at": item.cancelled_at}
                              for item in training_packages],
        "training_sessions": [{"performed_at": item.performed_at, "duration_minutes": item.duration_minutes,
                               "focus": item.focus, "notes": item.notes, "package_id": item.package_id}
                              for item in training_logs],
        "export_limitations": "This workspace export includes up to 5,000 rows per attendance, payment, retention case, training package and training session category, and 1,000 subscriptions. Processor records and backups are not included.",
    }
