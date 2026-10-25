"""Admin member directory & management API routes (Sections 8, 9, 7.6)."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, Header, HTTPException, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.api.deps import get_client_ip, get_session, require_capability, require_writable_org
from app.core.constants import MemberStatus, Role
from app.core.permissions import Capability, role_has
from app.core.tenancy import TenantContext
from app.services import idempotency_service
from app.schemas.common import Message
from app.schemas.members import (
    ApprovalDecision,
    ClientAssignment,
    EmailUpdate,
    FreezeRequestDecision,
    FreezeRequestOut,
    FreezeRequestQueueOut,
    MembershipChangeDecision,
    MembershipChangeOut,
    MembershipChangeQueueOut,
    FamilyLinkRequest,
    FamilyMemberOut,
    MemberDetailOut,
    MemberDirectoryItem,
    MemberInvite,
    MemberInviteOut,
    MemberProfileOut,
    MemberProfileUpdate,
    MemberTagsUpdate,
    MemberStatusChange,
    MemberSubscriptionOut,
    RoleChange,
    TrainerAssign,
    TrainerAssignment,
)
from app.schemas.organizations import BulkImportResult
from app.services import member_trainers_service as trainer_assign
from app.services.audit_service import record_audit
from app.services import members_service as members
from app.services import family_service as families
from app.services import membership_changes_service as member_changes
from app.models.membership import OrganizationMember
from app.models.organization import Organization
from app.models.user import User

router = APIRouter()


@router.get("/change-requests", response_model=list[MembershipChangeQueueOut])
async def membership_change_queue(
    status: str = "pending",
    ctx: TenantContext = Depends(require_capability(Capability.MANAGE_MEMBERS)),
    session: AsyncSession = Depends(get_session),
):
    rows = await member_changes.queue(session, org_id=ctx.org_id, status=status)
    return [MembershipChangeQueueOut(
        id=req.id, member_id=member.id, subscription_id=req.subscription_id,
        request_type=req.request_type, target_plan_id=req.target_plan_id,
        reason=req.reason, status=req.status, save_offer=req.save_offer,
        created_at=req.created_at, reviewed_at=req.reviewed_at, decision_note=req.decision_note,
        offer_type=req.offer_type, offer_plan_id=req.offer_plan_id,
        offer_discount_percent=req.offer_discount_percent, amount_due=req.amount_due,
        effective_at=req.effective_at,
        member_name=member.display_name or user.full_name or user.email, member_email=user.email,
        current_plan_name=current.name, target_plan_name=target.name if target else None,
    ) for req, member, user, current, target in rows]


@router.post("/change-requests/{request_id}/decision", response_model=MembershipChangeOut,
             dependencies=[Depends(require_writable_org)])
async def decide_membership_change(
    request_id: str, data: MembershipChangeDecision,
    ctx: TenantContext = Depends(require_capability(Capability.MANAGE_MEMBERS)),
    session: AsyncSession = Depends(get_session),
):
    if ctx.role not in {Role.OWNER, Role.MANAGER}:
        raise HTTPException(status_code=403, detail="Owner or manager access required.")
    return await member_changes.decide(
        session, org_id=ctx.org_id, request_id=request_id, actor_id=ctx.user_id,
        approve=data.approve, offer_pause=data.offer_pause, note=data.note,
        offer_type=data.offer_type, offer_plan_id=data.offer_plan_id,
        offer_discount_percent=data.offer_discount_percent,
        offer_discount_months=data.offer_discount_months, effective_timing=data.effective_timing,
    )


async def _trainer_names(session: AsyncSession, org_id: str) -> dict[str, list[str]]:
    """member_id -> sorted display names of its active trainers."""

    rows = await trainer_assign.org_assignments(session, org_id=org_id)
    names: dict[str, list[str]] = {}
    for _mt, t, u in rows:
        name = t.display_name or u.full_name or u.email
        names.setdefault(_mt.member_id, []).append(name)
    return {mid: sorted(ns) for mid, ns in names.items()}


def _item(m, u, trainers: list[str] | None = None, *, include_compensation: bool = False) -> MemberDirectoryItem:
    return MemberDirectoryItem(
        member_id=m.id, user_id=u.id, email=u.email, full_name=u.full_name,
        display_name=m.display_name,
        photo_url=m.photo_url,
        role=m.role.value, member_status=m.member_status.value, phone=m.phone,
        profile_complete=m.profile_complete,
        created_at=m.created_at,
        fixed_monthly_salary=m.fixed_monthly_salary if include_compensation else None,
        hourly_rate=m.hourly_rate if include_compensation else None,
        per_class_rate=m.per_class_rate if include_compensation else None,
        commission_rate=m.commission_rate if include_compensation else None,
        assigned_trainers=trainers or [],
        tags=m.tags,
    )


async def _item_with_trainers(
    session: AsyncSession, org_id: str, member, user, *, include_compensation: bool = False,
) -> MemberDirectoryItem:
    rows = await trainer_assign.list_for_member(session, org_id=org_id, member_id=member.id)
    names = sorted((t.display_name or u.full_name or u.email) for _mt, t, u in rows)
    return _item(member, user, trainers=names, include_compensation=include_compensation)


@router.get("", response_model=list[MemberDirectoryItem])
async def list_directory(
    status: MemberStatus | None = None,
    role: Role | None = None,
    ctx: TenantContext = Depends(require_capability(Capability.MANAGE_MEMBERS)),
    session: AsyncSession = Depends(get_session),
):
    rows = await members.directory(session, org_id=ctx.org_id, status=status, role=role)
    names = await _trainer_names(session, ctx.org_id)
    if rows and role_has(ctx.role, Capability.VIEW_STAFF_COMPENSATION):
        await record_audit(
            session, action="staff.compensation_viewed", organization_id=ctx.org_id,
            actor_user_id=ctx.user_id, entity_type="member_directory",
            metadata={"record_count": len(rows)},
        )
    return [_item(m, u, trainers=names.get(m.id), include_compensation=role_has(ctx.role, Capability.VIEW_STAFF_COMPENSATION)) for m, u in rows]


@router.get("/assigned-to-me", response_model=list[ClientAssignment])
async def assigned_to_me(
    ctx: TenantContext = Depends(require_capability(Capability.VIEW_ASSIGNED_MEMBERS)),
    session: AsyncSession = Depends(get_session),
):
    """Trainers see the members assigned to them; admins see the whole roster."""

    if ctx.role == Role.TRAINER:
        membership = (
            await session.execute(
                select(OrganizationMember).where(
                    OrganizationMember.organization_id == ctx.org_id,
                    OrganizationMember.user_id == ctx.user_id,
                )
            )
        ).scalar_one_or_none()
        if membership is None:
            raise HTTPException(status_code=404, detail="Trainer not found.")
        rows = await trainer_assign.clients_for_trainer(
            session, org_id=ctx.org_id, trainer_member_id=membership.id)
    else:
        rows = await trainer_assign.all_clients(session, org_id=ctx.org_id)

    result: list[ClientAssignment] = []
    for mt, m, u in rows:
        result.append(ClientAssignment(
            member_id=mt.member_id,
            member_name=m.display_name or u.full_name,
            member_email=u.email,
            member_status=m.member_status.value,
            assigned_at=mt.assigned_at,
        ))
    return result


@router.get("/approval-queue", response_model=list[MemberDirectoryItem])
async def approval_queue(
    ctx: TenantContext = Depends(require_capability(Capability.MANAGE_MEMBERS)),
    session: AsyncSession = Depends(get_session),
):
    rows = await members.approval_queue(session, org_id=ctx.org_id)
    names = await _trainer_names(session, ctx.org_id)
    if rows and role_has(ctx.role, Capability.VIEW_STAFF_COMPENSATION):
        await record_audit(
            session, action="staff.compensation_viewed", organization_id=ctx.org_id,
            actor_user_id=ctx.user_id, entity_type="member_directory",
            metadata={"record_count": len(rows)},
        )
    return [_item(m, u, trainers=names.get(m.id), include_compensation=role_has(ctx.role, Capability.VIEW_STAFF_COMPENSATION)) for m, u in rows]


@router.get("/freeze-requests", response_model=list[FreezeRequestQueueOut])
async def freeze_request_queue(
    status: str = "pending",
    ctx: TenantContext = Depends(require_capability(Capability.MANAGE_MEMBERS)),
    session: AsyncSession = Depends(get_session),
):
    if status not in {"pending", "approved", "rejected", "cancelled"}:
        raise HTTPException(status_code=422, detail="Invalid pause request status.")
    rows = await members.freeze_request_queue(session, org_id=ctx.org_id, status=status)
    return [FreezeRequestQueueOut(
        id=request.id, member_id=member.id, reason=request.reason,
        requested_until=request.requested_until, source=request.source, status=request.status,
        created_at=request.created_at, reviewed_at=request.reviewed_at,
        decision_note=request.decision_note, member_name=member.display_name or user.full_name or user.email,
        member_email=user.email,
    ) for request, member, user in rows]


@router.post("/freeze-requests/{request_id}/decision", response_model=FreezeRequestOut,
             dependencies=[Depends(require_writable_org)])
async def decide_freeze_request(
    request_id: str,
    data: FreezeRequestDecision,
    ctx: TenantContext = Depends(require_capability(Capability.MANAGE_MEMBERS)),
    session: AsyncSession = Depends(get_session),
):
    if ctx.role not in {Role.OWNER, Role.MANAGER}:
        raise HTTPException(status_code=403, detail="Owner or manager access required.")
    return await members.decide_freeze_request(
        session, org_id=ctx.org_id, request_id=request_id, approve=data.approve,
        note=data.note, actor_id=ctx.user_id,
    )


@router.get("/{member_id}", response_model=MemberDetailOut)
async def member_detail(
    member_id: str,
    request: Request,
    ctx: TenantContext = Depends(require_capability(Capability.MANAGE_MEMBERS)),
    session: AsyncSession = Depends(get_session),
):
    data = await members.member_detail(session, org_id=ctx.org_id, member_id=member_id)
    member, user = data["member"], data["user"]
    sub = data["subscription"]
    plan = data["plan"]
    family_owner = None
    if member.family_owner_member_id:
        owner = await session.get(OrganizationMember, member.family_owner_member_id)
        if owner and owner.organization_id == ctx.org_id:
            owner_user = await session.get(User, owner.user_id)
            family_owner = FamilyMemberOut(member_id=owner.id, name=owner.display_name or (owner_user.full_name or owner_user.email if owner_user else "Member"))
    family_rows = await families.family_members(session, ctx.org_id, member.id)
    family_members = []
    for family_member in family_rows:
        family_user = await session.get(User, family_member.user_id)
        family_members.append(FamilyMemberOut(
            member_id=family_member.id,
            name=family_member.display_name or (family_user.full_name or family_user.email if family_user else "Member"),
        ))

    subscription = None
    if sub is not None:
        subscription = MemberSubscriptionOut(
            subscription_id=sub.id,
            plan_id=sub.plan_id,
            plan_name=plan.name if plan else "Archived plan",
            plan_price=plan.price if plan else sub.price_snapshot,
            price_snapshot=sub.price_snapshot,
            currency=sub.currency,
            billing_type=plan.billing_type.value if plan else "recurring",
            status=sub.status.value,
            started_at=sub.started_at,
            current_period_end=sub.current_period_end,
            grace_until=sub.grace_until,
            frozen_until=sub.frozen_until,
            cancelled_at=sub.cancelled_at,
            classes_remaining=sub.classes_remaining,
            credits_allowance=sub.credits_allowance,
            audience=plan.audience if plan else "standard",
            family_capacity=plan.family_capacity if plan else None,
        )

    from app.api.v1.routes.payments import _to_out as payment_to_out

    rows = await trainer_assign.list_for_member(session, org_id=ctx.org_id, member_id=member.id)
    if role_has(ctx.role, Capability.VIEW_STAFF_COMPENSATION):
        await record_audit(
            session, action="staff.compensation_viewed", organization_id=ctx.org_id,
            actor_user_id=ctx.user_id, entity_type="member", entity_id=member.id,
            ip_address=get_client_ip(request), user_agent=request.headers.get("user-agent"),
        )
    private_access = role_has(ctx.role, Capability.VIEW_PRIVATE_MEMBER_PROFILE)
    private_fields = [
        field for field, value in (
            ("health_notes", member.health_notes),
            ("id_document", member.id_document_type or member.id_document_last4),
        ) if value
    ]
    if private_access and private_fields:
        await record_audit(
            session, action="member.private_profile_viewed", organization_id=ctx.org_id,
            actor_user_id=ctx.user_id, entity_type="member", entity_id=member.id,
            ip_address=get_client_ip(request), user_agent=request.headers.get("user-agent"),
            metadata={"fields": private_fields},
        )
    names = sorted((t.display_name or u.full_name or u.email) for _mt, t, u in rows)
    trainer_assignments = [
        TrainerAssignment(
            member_id=mt.member_id, trainer_member_id=mt.trainer_member_id,
            trainer_name=t.display_name or u.full_name or u.email,
            assigned_at=mt.assigned_at, active=mt.active,
        )
        for mt, t, u in rows
    ]

    return MemberDetailOut(
        member=_item(member, user, trainers=names, include_compensation=role_has(ctx.role, Capability.VIEW_STAFF_COMPENSATION)),
        profile=MemberProfileOut(
            display_name=member.display_name, phone=member.phone,
            photo_url=member.photo_url, emergency_contact=member.emergency_contact,
            goals=member.goals, health_notes=member.health_notes if private_access else None,
            id_document_type=member.id_document_type if private_access else None,
            id_document_last4=member.id_document_last4 if private_access else None,
            summary=members.profile_summary(member, plan, include_private=private_access),
        ),
        subscription=subscription,
        payments=[payment_to_out(p) for p in data["payments"]],
        pending_payments=data["pending_payments"],
        trainer_assignments=trainer_assignments,
        family_owner=family_owner,
        family_members=family_members,
    )


@router.put("/{member_id}/tags", response_model=MemberTagsUpdate, dependencies=[Depends(require_writable_org)])
async def update_member_tags(
    member_id: str,
    data: MemberTagsUpdate,
    ctx: TenantContext = Depends(require_capability(Capability.MANAGE_MEMBERS)),
    session: AsyncSession = Depends(get_session),
):
    member = await members._get_member(session, ctx.org_id, member_id)
    if member.tags != data.tags:
        member.tags = data.tags
        session.add(member)
        await record_audit(
            session, action="member.tags_updated", organization_id=ctx.org_id,
            actor_user_id=ctx.user_id, entity_type="member", entity_id=member.id,
            metadata={"tag_count": len(data.tags)},
        )
    return MemberTagsUpdate(tags=member.tags)


@router.post("/{member_id}/family", response_model=Message, dependencies=[Depends(require_writable_org)])
async def add_family_member(
    member_id: str,
    data: FamilyLinkRequest,
    ctx: TenantContext = Depends(require_capability(Capability.MANAGE_MEMBERS)),
    session: AsyncSession = Depends(get_session),
):
    if ctx.role not in {Role.OWNER, Role.MANAGER}:
        raise HTTPException(status_code=403, detail="Owner or manager access required.")
    await families.set_family_member(
        session, org_id=ctx.org_id, owner_id=member_id,
        dependent_id=data.member_id, attach=True, actor_id=ctx.user_id,
    )
    return Message(message="Member added to family plan.")


@router.delete("/{member_id}/family/{dependent_id}", response_model=Message, dependencies=[Depends(require_writable_org)])
async def remove_family_member(
    member_id: str,
    dependent_id: str,
    ctx: TenantContext = Depends(require_capability(Capability.MANAGE_MEMBERS)),
    session: AsyncSession = Depends(get_session),
):
    if ctx.role not in {Role.OWNER, Role.MANAGER}:
        raise HTTPException(status_code=403, detail="Owner or manager access required.")
    await families.set_family_member(
        session, org_id=ctx.org_id, owner_id=member_id,
        dependent_id=dependent_id, attach=False, actor_id=ctx.user_id,
    )
    return Message(message="Member removed from family plan.")


@router.patch("/{member_id}/profile", response_model=MemberProfileOut)
async def update_profile(
    member_id: str,
    data: MemberProfileUpdate,
    ctx: TenantContext = Depends(require_capability(Capability.MANAGE_MEMBERS)),
    org: Organization = Depends(require_writable_org),
    session: AsyncSession = Depends(get_session),
):
    private_access = role_has(ctx.role, Capability.VIEW_PRIVATE_MEMBER_PROFILE)
    if not private_access and data.model_fields_set & {"health_notes", "id_document_type", "id_document_last4"}:
        raise HTTPException(status_code=403, detail="Private profile details require owner or manager access.")
    member = await members.update_member_profile(
        session, org_id=ctx.org_id, member_id=member_id,
        data=data, actor_id=ctx.user_id,
    )
    detail = await members.member_detail(session, org_id=ctx.org_id, member_id=member_id)
    return MemberProfileOut(
        display_name=member.display_name, phone=member.phone,
        photo_url=member.photo_url, emergency_contact=member.emergency_contact,
        goals=member.goals, health_notes=member.health_notes if private_access else None,
        id_document_type=member.id_document_type if private_access else None,
        id_document_last4=member.id_document_last4 if private_access else None,
        summary=members.profile_summary(member, detail["plan"], include_private=private_access),
    )


@router.post("/{member_id}/approval", response_model=MemberDirectoryItem)
async def decide_approval(
    member_id: str,
    data: ApprovalDecision,
    ctx: TenantContext = Depends(require_capability(Capability.MANAGE_MEMBERS)),
    session: AsyncSession = Depends(get_session),
):
    member = await members.decide_approval(session, org_id=ctx.org_id, member_id=member_id,
                                            approve=data.approve, reason=data.reason, actor_id=ctx.user_id)
    user = await session.get(User, member.user_id)
    return await _item_with_trainers(session, ctx.org_id, member, user, include_compensation=role_has(ctx.role, Capability.VIEW_STAFF_COMPENSATION))


@router.post("/{member_id}/status", response_model=MemberDirectoryItem)
async def change_status(
    member_id: str,
    data: MemberStatusChange,
    ctx: TenantContext = Depends(require_capability(Capability.MANAGE_MEMBERS)),
    session: AsyncSession = Depends(get_session),
):
    member = await members.change_status(session, org_id=ctx.org_id, member_id=member_id,
                                          action=data.action, reason=data.reason, actor_id=ctx.user_id)
    user = await session.get(User, member.user_id)
    return await _item_with_trainers(session, ctx.org_id, member, user, include_compensation=role_has(ctx.role, Capability.VIEW_STAFF_COMPENSATION))


@router.patch("/{member_id}/role", response_model=MemberDirectoryItem)
async def change_role(
    member_id: str,
    data: RoleChange,
    ctx: TenantContext = Depends(require_capability(Capability.MANAGE_MEMBERS)),
    session: AsyncSession = Depends(get_session),
):
    member = await members.change_role(session, org_id=ctx.org_id, member_id=member_id,
                                        new_role=data.role, actor_id=ctx.user_id, actor_role=ctx.role)
    user = await session.get(User, member.user_id)
    return await _item_with_trainers(session, ctx.org_id, member, user, include_compensation=role_has(ctx.role, Capability.VIEW_STAFF_COMPENSATION))


@router.patch("/{member_id}/email", response_model=MemberDirectoryItem)
async def change_email(
    member_id: str,
    data: EmailUpdate,
    ctx: TenantContext = Depends(require_capability(Capability.MANAGE_MEMBERS)),
    session: AsyncSession = Depends(get_session),
):
    member = await members.update_email(session, org_id=ctx.org_id, member_id=member_id,
                                         new_email=data.email, actor_id=ctx.user_id)
    user = await session.get(User, member.user_id)
    return await _item_with_trainers(session, ctx.org_id, member, user, include_compensation=role_has(ctx.role, Capability.VIEW_STAFF_COMPENSATION))


@router.delete("/{member_id}", response_model=Message)
async def delete_member(
    member_id: str,
    ctx: TenantContext = Depends(require_capability(Capability.MANAGE_MEMBERS)),
    session: AsyncSession = Depends(get_session),
):
    await members.delete_member(session, org_id=ctx.org_id, member_id=member_id,
                                actor_user_id=ctx.user_id, actor_role=ctx.role)
    return Message(message="Member deleted.")


# ------------------------------------------------------------- trainer assignment
@router.get("/{member_id}/trainers", response_model=list[TrainerAssignment])
async def list_member_trainers(
    member_id: str,
    ctx: TenantContext = Depends(require_capability(Capability.ASSIGN_TRAINERS)),
    session: AsyncSession = Depends(get_session),
):
    rows = await trainer_assign.list_for_member(session, org_id=ctx.org_id, member_id=member_id)
    return [
        TrainerAssignment(
            member_id=mt.member_id, trainer_member_id=mt.trainer_member_id,
            trainer_name=t.display_name or u.full_name or u.email,
            assigned_at=mt.assigned_at, active=mt.active,
        )
        for mt, t, u in rows
    ]


@router.post("/{member_id}/trainers", response_model=TrainerAssignment, status_code=201)
async def assign_trainer(
    member_id: str,
    data: TrainerAssign,
    idempotency_key: str = Header(default="", alias="Idempotency-Key"),
    ctx: TenantContext = Depends(require_capability(Capability.ASSIGN_TRAINERS)),
    org: Organization = Depends(require_writable_org),
    session: AsyncSession = Depends(get_session),
):
    claim = None
    if idempotency_key:
        claim = await idempotency_service.claim(
            session, key=idempotency_key, endpoint=f"member.trainer_assign:{ctx.org_id}:{ctx.user_id}:{member_id}",
            body=data.model_dump(mode="json"), organization_id=ctx.org_id, user_id=ctx.user_id,
        )
        if not claim.claimed:
            return TrainerAssignment.model_validate_json(claim.cached_response or "{}")
    mt = await trainer_assign.assign(
        session, org_id=ctx.org_id, member_id=member_id,
        trainer_member_id=data.trainer_member_id, actor_user_id=ctx.user_id)
    trainer = await session.get(OrganizationMember, mt.trainer_member_id)
    user = await session.get(User, trainer.user_id) if trainer else None
    output = TrainerAssignment(
        member_id=mt.member_id, trainer_member_id=mt.trainer_member_id,
        trainer_name=(trainer.display_name or user.full_name or user.email) if user else "—",
        assigned_at=mt.assigned_at, active=mt.active,
    )
    if claim:
        await idempotency_service.complete(session, claim.record, code=201, body=output.model_dump_json())
    return output


@router.delete("/{member_id}/trainers/{trainer_member_id}", response_model=Message)
async def unassign_trainer(
    member_id: str,
    trainer_member_id: str,
    ctx: TenantContext = Depends(require_capability(Capability.ASSIGN_TRAINERS)),
    org: Organization = Depends(require_writable_org),
    session: AsyncSession = Depends(get_session),
):
    await trainer_assign.unassign(
        session, org_id=ctx.org_id, member_id=member_id,
        trainer_member_id=trainer_member_id, actor_user_id=ctx.user_id)
    return Message(message="Trainer unassigned.")


def _invite_out(member, email: str, code: str, delivered: bool) -> MemberInviteOut:
    """Only expose the raw invite code when delivery actually failed (or no
    provider is configured); otherwise the code goes out by email and must stay
    secret. ``delivered`` is the send's own result, not a config check."""

    return MemberInviteOut(
        member_id=member.id, email=email, member_status=member.member_status.value,
        email_delivered=delivered,
        invite_code="" if delivered else code,
    )


@router.post("/invite", response_model=MemberInviteOut, status_code=201)
async def invite_member(
    data: MemberInvite,
    ctx: TenantContext = Depends(require_capability(Capability.INVITE_MEMBERS)),
    session: AsyncSession = Depends(get_session),
):
    member, code, delivered = await members.invite_member(session, org_id=ctx.org_id, email=data.email,
                                                          actor_id=ctx.user_id)
    return _invite_out(member, data.email, code, delivered)


@router.post("/{member_id}/resend-invite", response_model=MemberInviteOut)
async def resend_invite(
    member_id: str,
    ctx: TenantContext = Depends(require_capability(Capability.INVITE_MEMBERS)),
    session: AsyncSession = Depends(get_session),
):
    member, code, delivered = await members.resend_invite(session, org_id=ctx.org_id, member_id=member_id,
                                                          actor_id=ctx.user_id)
    user = await session.get(User, member.user_id)
    return _invite_out(member, user.email, code, delivered)


@router.post("/import", response_model=BulkImportResult, status_code=201)
async def bulk_import(
    file: UploadFile = File(...),
    ctx: TenantContext = Depends(require_capability(Capability.MANAGE_MEMBERS)),
    session: AsyncSession = Depends(get_session),
):
    """Bulk-import members from CSV or XLSX (web-only, Section 9.9, 16)."""

    content = await file.read(2_000_001)
    if not content:
        raise HTTPException(status_code=422, detail="Uploaded file is empty.")
    if len(content) > 2_000_000:
        raise HTTPException(status_code=413, detail="Import files must be 2 MB or smaller.")
    extension = Path(file.filename or "").suffix.lower()
    if extension not in {".csv", ".xlsx"}:
        raise HTTPException(status_code=422, detail="Upload a CSV or .xlsx workbook.")
    if extension == ".xlsx":
        content = members.xlsx_as_csv(content)
    result = await members.bulk_import_csv(session, org_id=ctx.org_id, csv_bytes=content,
                                           actor_id=ctx.user_id)
    return BulkImportResult(**result)
