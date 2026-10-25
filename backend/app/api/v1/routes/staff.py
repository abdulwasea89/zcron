"""Staff API routes: invites, shifts, tasks, compensation (Sections 15-17)."""

from __future__ import annotations

from datetime import timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.api.deps import get_session, require_capability, require_writable_org
from app.core.constants import Role
from app.core.permissions import Capability
from app.core.tenancy import TenantContext
from app.models.membership import OrganizationMember
from app.models.user import User
from app.models.base import utcnow
from app.models.staff import ScheduledShift
from app.models.trainer_availability import TrainerAvailability
from app.schemas.auth import LoginResponse
from app.schemas.common import Message
from app.schemas.staff import (
    CompensationUpdate,
    InviteEmailUpdate,
    InviteRoleUpdate,
    ShiftOut,
    ShiftScheduleCreate,
    ShiftScheduleOut,
    StaffInviteCreate,
    StaffInviteOut,
    StaffInviteRedeem,
    TaskCreateIn,
    TaskOut,
    TaskUpdateIn,
    TrainerSessionCreate,
    TrainerSessionOut,
    TrainerAvailabilityCreate,
    TrainerAvailabilityOut,
)
from app.services import staff_service as staff
from app.services import trainer_sessions_service as trainer_sessions
from app.services.audit_service import record_audit

router = APIRouter()


@router.get("/availability", response_model=list[TrainerAvailabilityOut])
async def list_trainer_availability(
    ctx: TenantContext = Depends(require_capability(Capability.VIEW_ASSIGNED_MEMBERS)),
    session: AsyncSession = Depends(get_session),
):
    statement = select(TrainerAvailability).where(
        TrainerAvailability.organization_id == ctx.org_id,
    )
    if ctx.role == Role.TRAINER:
        statement = statement.where(
            TrainerAvailability.trainer_member_id == await _actor_member_id(session, ctx)
        )
    rows = (await session.execute(
        statement.order_by(TrainerAvailability.weekday, TrainerAvailability.start_time)
    )).scalars().all()
    return [TrainerAvailabilityOut.model_validate(row) for row in rows]


@router.post("/availability", response_model=TrainerAvailabilityOut, status_code=201,
             dependencies=[Depends(require_writable_org)])
async def create_trainer_availability(
    data: TrainerAvailabilityCreate,
    ctx: TenantContext = Depends(require_capability(Capability.ASSIGN_TRAINERS)),
    session: AsyncSession = Depends(get_session),
):
    trainer = await session.get(OrganizationMember, data.trainer_member_id)
    if (
        trainer is None or trainer.organization_id != ctx.org_id
        or trainer.role != Role.TRAINER or trainer.banned
    ):
        raise HTTPException(status_code=404, detail="Trainer not found.")
    overlap = (await session.execute(select(TrainerAvailability.id).where(
        TrainerAvailability.organization_id == ctx.org_id,
        TrainerAvailability.trainer_member_id == trainer.id,
        TrainerAvailability.weekday == data.weekday,
        TrainerAvailability.start_time < data.end_time,
        TrainerAvailability.end_time > data.start_time,
    ).limit(1))).scalar_one_or_none()
    if overlap:
        raise HTTPException(status_code=409, detail="This availability overlaps an existing window.")
    availability = TrainerAvailability(
        organization_id=ctx.org_id,
        trainer_member_id=trainer.id,
        weekday=data.weekday,
        start_time=data.start_time,
        end_time=data.end_time,
    )
    session.add(availability)
    await session.flush()
    await record_audit(
        session, action="staff.trainer_availability_created", organization_id=ctx.org_id,
        actor_user_id=ctx.user_id, entity_type="trainer_availability", entity_id=availability.id,
    )
    return TrainerAvailabilityOut.model_validate(availability)


@router.delete("/availability/{availability_id}", response_model=Message,
               dependencies=[Depends(require_writable_org)])
async def delete_trainer_availability(
    availability_id: str,
    ctx: TenantContext = Depends(require_capability(Capability.ASSIGN_TRAINERS)),
    session: AsyncSession = Depends(get_session),
):
    availability = await session.get(TrainerAvailability, availability_id)
    if availability is None or availability.organization_id != ctx.org_id:
        raise HTTPException(status_code=404, detail="Availability window not found.")
    await record_audit(
        session, action="staff.trainer_availability_deleted", organization_id=ctx.org_id,
        actor_user_id=ctx.user_id, entity_type="trainer_availability", entity_id=availability.id,
    )
    await session.delete(availability)
    return Message(message="Availability window removed.")


@router.get("/trainer-sessions", response_model=list[TrainerSessionOut])
async def list_trainer_sessions(
    client_member_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    ctx: TenantContext = Depends(require_capability(Capability.VIEW_ASSIGNED_MEMBERS)),
    session: AsyncSession = Depends(get_session),
):
    trainer_id = await _actor_member_id(session, ctx) if ctx.role == Role.TRAINER else None
    return await trainer_sessions.list_logs(
        session, org_id=ctx.org_id, trainer_member_id=trainer_id,
        client_member_id=client_member_id, limit=limit,
    )


@router.post("/trainer-sessions", response_model=TrainerSessionOut, status_code=201,
             dependencies=[Depends(require_writable_org)])
async def create_trainer_session(
    data: TrainerSessionCreate,
    ctx: TenantContext = Depends(require_capability(Capability.VIEW_ASSIGNED_MEMBERS)),
    session: AsyncSession = Depends(get_session),
):
    if ctx.role != Role.TRAINER:
        raise HTTPException(status_code=403, detail="Only trainers can log their own sessions.")
    trainer_id = await _actor_member_id(session, ctx)
    log = await trainer_sessions.create_log(
        session, org_id=ctx.org_id, trainer_member_id=trainer_id,
        actor_id=ctx.user_id, data=data,
    )
    client = await session.get(OrganizationMember, log.client_member_id)
    user = await session.get(User, client.user_id)
    return TrainerSessionOut(
        id=log.id, client_member_id=client.id,
        client_name=client.display_name or user.full_name or user.email,
        performed_at=log.performed_at, duration_minutes=log.duration_minutes,
        focus=log.focus, notes=log.notes,
    )


@router.get("/schedule", response_model=list[ShiftScheduleOut])
async def list_shift_schedule(
    ctx: TenantContext = Depends(require_capability(Capability.MANAGE_MEMBERS)),
    session: AsyncSession = Depends(get_session),
):
    rows = (await session.execute(
        select(ScheduledShift).where(
            ScheduledShift.organization_id == ctx.org_id,
            ScheduledShift.ends_at >= utcnow(),
        ).order_by(ScheduledShift.starts_at).limit(200)
    )).scalars()
    return [ShiftScheduleOut(id=s.id, staff_member_id=s.staff_member_id, starts_at=s.starts_at,
                             ends_at=s.ends_at, note=s.note) for s in rows]


@router.get("/schedule/mine", response_model=list[ShiftScheduleOut])
async def list_my_shift_schedule(
    ctx: TenantContext = Depends(require_capability(Capability.CHECK_IN_SHIFT)),
    session: AsyncSession = Depends(get_session),
):
    member_id = await _actor_member_id(session, ctx)
    rows = (await session.execute(
        select(ScheduledShift).where(
            ScheduledShift.organization_id == ctx.org_id,
            ScheduledShift.staff_member_id == member_id,
            ScheduledShift.ends_at >= utcnow(),
        ).order_by(ScheduledShift.starts_at).limit(50)
    )).scalars()
    return [ShiftScheduleOut(id=s.id, staff_member_id=s.staff_member_id, starts_at=s.starts_at,
                             ends_at=s.ends_at, note=s.note) for s in rows]


@router.post("/schedule", response_model=ShiftScheduleOut, status_code=201,
             dependencies=[Depends(require_writable_org)])
async def create_shift_schedule(
    data: ShiftScheduleCreate,
    ctx: TenantContext = Depends(require_capability(Capability.MANAGE_MEMBERS)),
    session: AsyncSession = Depends(get_session),
):
    member = await session.get(OrganizationMember, data.staff_member_id)
    if member is None or member.organization_id != ctx.org_id or member.role not in {Role.MANAGER, Role.TRAINER, Role.FRONT_DESK}:
        raise HTTPException(status_code=404, detail="Staff member not found.")
    starts_at = data.starts_at.astimezone(timezone.utc).replace(tzinfo=None) if data.starts_at.tzinfo else data.starts_at
    ends_at = data.ends_at.astimezone(timezone.utc).replace(tzinfo=None) if data.ends_at.tzinfo else data.ends_at
    conflict = (await session.execute(select(ScheduledShift.id).where(
        ScheduledShift.organization_id == ctx.org_id,
        ScheduledShift.staff_member_id == member.id,
        ScheduledShift.starts_at < ends_at,
        ScheduledShift.ends_at > starts_at,
    ).limit(1))).first()
    if conflict:
        raise HTTPException(status_code=409, detail="This staff member already has an overlapping shift.")
    # shortcut: concurrent requests can both pass this check; add a database exclusion constraint if parallel scheduling becomes common.
    scheduled = ScheduledShift(organization_id=ctx.org_id, staff_member_id=member.id,
                               starts_at=starts_at, ends_at=ends_at, note=data.note,
                               assigned_by=ctx.user_id)
    session.add(scheduled)
    await session.flush()
    await record_audit(session, action="staff.shift_scheduled", organization_id=ctx.org_id,
                       actor_user_id=ctx.user_id, entity_type="scheduled_shift", entity_id=scheduled.id,
                       new_values={"staff_member_id": member.id, "starts_at": starts_at,
                                   "ends_at": ends_at, "note": data.note})
    return ShiftScheduleOut(id=scheduled.id, staff_member_id=scheduled.staff_member_id,
                            starts_at=scheduled.starts_at, ends_at=scheduled.ends_at, note=scheduled.note)


@router.delete("/schedule/{schedule_id}", response_model=Message,
               dependencies=[Depends(require_writable_org)])
async def delete_shift_schedule(
    schedule_id: str,
    ctx: TenantContext = Depends(require_capability(Capability.MANAGE_MEMBERS)),
    session: AsyncSession = Depends(get_session),
):
    scheduled = await session.get(ScheduledShift, schedule_id)
    if scheduled is None or scheduled.organization_id != ctx.org_id:
        raise HTTPException(status_code=404, detail="Scheduled shift not found.")
    await record_audit(session, action="staff.shift_schedule_removed", organization_id=ctx.org_id,
                       actor_user_id=ctx.user_id, entity_type="scheduled_shift", entity_id=scheduled.id,
                       old_values={"staff_member_id": scheduled.staff_member_id,
                                   "starts_at": scheduled.starts_at, "ends_at": scheduled.ends_at,
                                   "note": scheduled.note})
    await session.delete(scheduled)
    return Message(message="Scheduled shift removed.")


@router.post("/invites", response_model=StaffInviteOut, status_code=201)
async def create_invite(
    data: StaffInviteCreate,
    ctx: TenantContext = Depends(require_capability(Capability.MANAGE_MEMBERS)),
    session: AsyncSession = Depends(get_session),
):
    invite = await staff.create_invite(session, org_id=ctx.org_id, data=data, actor_id=ctx.user_id)
    return StaffInviteOut(id=invite.id, code=invite.code, role=invite.role,
                          email=invite.email, used=invite.used)


@router.get("/invites", response_model=list[StaffInviteOut])
async def list_invites(
    ctx: TenantContext = Depends(require_capability(Capability.MANAGE_MEMBERS)),
    session: AsyncSession = Depends(get_session),
):
    return [
        StaffInviteOut(id=i.id, code=i.code, role=i.role, email=i.email, used=i.used)
        for i in await staff.list_invites(session, org_id=ctx.org_id)
    ]


@router.patch("/invites/{invite_id}/email", response_model=StaffInviteOut)
async def update_invite_email(
    invite_id: str,
    data: InviteEmailUpdate,
    ctx: TenantContext = Depends(require_capability(Capability.MANAGE_MEMBERS)),
    session: AsyncSession = Depends(get_session),
):
    invite = await staff.update_invite_email(session, org_id=ctx.org_id, invite_id=invite_id,
                                              email=data.email, actor_id=ctx.user_id)
    return StaffInviteOut(id=invite.id, code=invite.code, role=invite.role,
                          email=invite.email, used=invite.used)


@router.patch("/invites/{invite_id}/role", response_model=StaffInviteOut)
async def update_invite_role(
    invite_id: str,
    data: InviteRoleUpdate,
    ctx: TenantContext = Depends(require_capability(Capability.MANAGE_MEMBERS)),
    session: AsyncSession = Depends(get_session),
):
    invite = await staff.update_invite_role(session, org_id=ctx.org_id, invite_id=invite_id,
                                             role=data.role, actor_id=ctx.user_id)
    return StaffInviteOut(id=invite.id, code=invite.code, role=invite.role,
                          email=invite.email, used=invite.used)


@router.delete("/invites/{invite_id}", response_model=Message)
async def revoke_invite(
    invite_id: str,
    ctx: TenantContext = Depends(require_capability(Capability.MANAGE_MEMBERS)),
    session: AsyncSession = Depends(get_session),
):
    await staff.revoke_invite(session, org_id=ctx.org_id, invite_id=invite_id, actor_id=ctx.user_id)
    return Message(message="Invite revoked.")


@router.post("/invites/redeem", response_model=LoginResponse)
async def redeem_invite(data: StaffInviteRedeem, session: AsyncSession = Depends(get_session)):
    member, access, refresh = await staff.redeem_invite(
        session, code=data.code, full_name=data.full_name, password=data.password
    )
    return LoginResponse(access_token=access, refresh_token=refresh,
                         organization_id=member.organization_id, role=member.role.value)


@router.patch("/{staff_member_id}/compensation", response_model=Message)
async def set_compensation(
    staff_member_id: str,
    data: CompensationUpdate,
    ctx: TenantContext = Depends(require_capability(Capability.RUN_PAYROLL)),
    session: AsyncSession = Depends(get_session),
):
    await staff.set_compensation(session, org_id=ctx.org_id, staff_member_id=staff_member_id,
                                 data=data, actor_id=ctx.user_id)
    return Message(message="Compensation updated.")


@router.get("/shifts/current", response_model=ShiftOut | None)
async def shift_current(
    ctx: TenantContext = Depends(require_capability(Capability.CHECK_IN_SHIFT)),
    session: AsyncSession = Depends(get_session),
):
    s = await staff.get_current_shift(session, org_id=ctx.org_id, user_id=ctx.user_id)
    if s is None:
        return None
    return ShiftOut(id=s.id, staff_member_id=s.staff_member_id, checked_in_at=s.checked_in_at,
                    checked_out_at=s.checked_out_at, status=s.status.value, hours=s.hours)


@router.post("/shifts/check-in", response_model=ShiftOut, status_code=201)
async def shift_check_in(
    ctx: TenantContext = Depends(require_capability(Capability.CHECK_IN_SHIFT)),
    session: AsyncSession = Depends(get_session),
):
    s = await staff.check_in(session, org_id=ctx.org_id, user_id=ctx.user_id)
    return ShiftOut(id=s.id, staff_member_id=s.staff_member_id, checked_in_at=s.checked_in_at,
                    checked_out_at=s.checked_out_at, status=s.status.value, hours=s.hours)


@router.post("/shifts/check-out", response_model=ShiftOut)
async def shift_check_out(
    ctx: TenantContext = Depends(require_capability(Capability.CHECK_IN_SHIFT)),
    session: AsyncSession = Depends(get_session),
):
    s = await staff.check_out(session, org_id=ctx.org_id, user_id=ctx.user_id)
    return ShiftOut(id=s.id, staff_member_id=s.staff_member_id, checked_in_at=s.checked_in_at,
                    checked_out_at=s.checked_out_at, status=s.status.value, hours=s.hours)


async def _actor_member_id(session: AsyncSession, ctx: TenantContext) -> str:
    member = (
        await session.execute(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == ctx.org_id,
                OrganizationMember.user_id == ctx.user_id,
            )
        )
    ).scalar_one_or_none()
    return member.id if member else ""


@router.post("/tasks", response_model=TaskOut, status_code=201)
async def create_task(
    data: TaskCreateIn,
    ctx: TenantContext = Depends(require_capability(Capability.ASSIGN_TASKS)),
    session: AsyncSession = Depends(get_session),
):
    actor_member_id = await _actor_member_id(session, ctx)
    task = await staff.create_task(session, org_id=ctx.org_id, data=data, actor_user_id=ctx.user_id,
                                   actor_role=ctx.role, actor_member_id=actor_member_id)
    return TaskOut(id=task.id, title=task.title, description=task.description, assignee_member_id=task.assignee_member_id,
                   deadline=task.deadline, done=task.done)


@router.get("/tasks", response_model=list[TaskOut])
async def list_tasks(
    ctx: TenantContext = Depends(require_capability(Capability.ASSIGN_TASKS)),
    session: AsyncSession = Depends(get_session),
):
    assignee_member_id = (
        await _actor_member_id(session, ctx) if ctx.role == Role.TRAINER else None
    )
    return [
        TaskOut(id=t.id, title=t.title, description=t.description, assignee_member_id=t.assignee_member_id,
                deadline=t.deadline, done=t.done)
        for t in await staff.list_tasks(
            session, org_id=ctx.org_id, assignee_member_id=assignee_member_id
        )
    ]


@router.post("/tasks/{task_id}/complete", response_model=TaskOut)
async def complete_task(
    task_id: str,
    ctx: TenantContext = Depends(require_capability(Capability.ASSIGN_TASKS)),
    session: AsyncSession = Depends(get_session),
):
    actor_member_id = await _actor_member_id(session, ctx)
    task = await staff.complete_task(
        session, org_id=ctx.org_id, task_id=task_id, actor_role=ctx.role,
        actor_member_id=actor_member_id,
    )
    return TaskOut(id=task.id, title=task.title, description=task.description, assignee_member_id=task.assignee_member_id,
                   deadline=task.deadline, done=task.done)


@router.patch("/tasks/{task_id}", response_model=TaskOut)
async def update_task(
    task_id: str,
    data: TaskUpdateIn,
    ctx: TenantContext = Depends(require_capability(Capability.ASSIGN_TASKS)),
    session: AsyncSession = Depends(get_session),
):
    actor_member_id = await _actor_member_id(session, ctx)
    task = await staff.update_task(
        session, org_id=ctx.org_id, task_id=task_id, data=data, actor_role=ctx.role,
        actor_member_id=actor_member_id,
    )
    return TaskOut(id=task.id, title=task.title, description=task.description, assignee_member_id=task.assignee_member_id,
                   deadline=task.deadline, done=task.done)


@router.delete("/tasks/{task_id}", response_model=Message)
async def delete_task(
    task_id: str,
    ctx: TenantContext = Depends(require_capability(Capability.ASSIGN_TASKS)),
    session: AsyncSession = Depends(get_session),
):
    actor_member_id = await _actor_member_id(session, ctx)
    await staff.delete_task(
        session, org_id=ctx.org_id, task_id=task_id, actor_role=ctx.role,
        actor_member_id=actor_member_id,
    )
    return Message(message="Task deleted.")
