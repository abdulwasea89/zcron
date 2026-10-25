"""Trainer-owned workout/session notes for assigned gym clients."""

from __future__ import annotations

from datetime import timezone

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.constants import MemberStatus, Role
from app.core.security import now_utc
from app.models.member_trainer import MemberTrainer
from app.models.membership import OrganizationMember
from app.models.trainer_session import TrainerSessionLog
from app.models.user import User
from app.schemas.staff import TrainerSessionCreate
from app.services.audit_service import record_audit


async def list_logs(
    session: AsyncSession, *, org_id: str, trainer_member_id: str | None,
    client_member_id: str | None, limit: int = 50,
) -> list[dict]:
    stmt = (
        select(TrainerSessionLog, OrganizationMember, User)
        .join(OrganizationMember, OrganizationMember.id == TrainerSessionLog.client_member_id)
        .join(User, User.id == OrganizationMember.user_id)
        .where(TrainerSessionLog.organization_id == org_id)
    )
    if trainer_member_id:
        stmt = stmt.where(TrainerSessionLog.trainer_member_id == trainer_member_id)
    if client_member_id:
        stmt = stmt.where(TrainerSessionLog.client_member_id == client_member_id)
    rows = (await session.execute(
        stmt.order_by(TrainerSessionLog.performed_at.desc(), TrainerSessionLog.id).limit(limit)
    )).all()
    return [{
        "id": log.id,
        "client_member_id": member.id,
        "client_name": member.display_name or user.full_name or user.email,
        "performed_at": log.performed_at,
        "duration_minutes": log.duration_minutes,
        "focus": log.focus,
        "notes": log.notes,
        "package_id": log.package_id,
    } for log, member, user in rows]


async def create_log(
    session: AsyncSession, *, org_id: str, trainer_member_id: str,
    actor_id: str, data: TrainerSessionCreate,
) -> TrainerSessionLog:
    trainer = await session.get(OrganizationMember, trainer_member_id)
    client = await session.get(OrganizationMember, data.client_member_id)
    if trainer is None or trainer.organization_id != org_id or trainer.role != Role.TRAINER or trainer.banned:
        raise HTTPException(status_code=403, detail="Trainer account is not available.")
    if client is None or client.organization_id != org_id or client.role != Role.MEMBER:
        raise HTTPException(status_code=404, detail="Member not found in this gym.")
    if client.member_status != MemberStatus.ACTIVE or client.banned:
        raise HTTPException(status_code=409, detail="Only active assigned members can have a training log.")
    assignment = (await session.execute(select(MemberTrainer.id).where(
        MemberTrainer.organization_id == org_id,
        MemberTrainer.trainer_member_id == trainer_member_id,
        MemberTrainer.member_id == client.id,
        MemberTrainer.active == True,  # noqa: E712
    ).limit(1))).first()
    if assignment is None:
        raise HTTPException(status_code=403, detail="You can only log sessions for members assigned to you.")
    performed_at = data.performed_at.astimezone(timezone.utc).replace(tzinfo=None) if data.performed_at.tzinfo else data.performed_at
    if performed_at > now_utc():
        raise HTTPException(status_code=422, detail="Training sessions cannot be logged in the future.")
    if data.package_id:
        from app.services.trainer_packages_service import consume_package

        await consume_package(session, org_id=org_id, package_id=data.package_id,
                              trainer_member_id=trainer_member_id, member_id=client.id, actor_id=actor_id)
    log = TrainerSessionLog(
        organization_id=org_id,
        trainer_member_id=trainer_member_id,
        client_member_id=client.id,
        package_id=data.package_id,
        performed_at=performed_at,
        duration_minutes=data.duration_minutes,
        focus=data.focus.strip(),
        notes=data.notes.strip(),
    )
    session.add(log)
    await session.flush()
    await record_audit(session, action="trainer.session_logged", organization_id=org_id,
                       actor_user_id=actor_id, entity_type="trainer_session_log", entity_id=log.id,
                       new_values={"client_member_id": client.id, "performed_at": performed_at,
                                   "duration_minutes": log.duration_minutes, "focus": log.focus})
    return log
