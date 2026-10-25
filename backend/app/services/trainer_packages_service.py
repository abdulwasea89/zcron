"""Admin grants and trainer consumption of personal-training session credits."""

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from sqlmodel import select

from app.core.constants import MemberStatus, Role
from app.core.security import now_utc
from app.models.member_trainer import MemberTrainer
from app.models.membership import OrganizationMember
from app.models.trainer_package import TrainerPackage
from app.models.user import User
from app.schemas.staff import TrainerPackageCreate
from app.services.audit_service import record_audit


async def create_package(session: AsyncSession, *, org_id: str, actor_id: str,
                         data: TrainerPackageCreate) -> TrainerPackage:
    member = await session.get(OrganizationMember, data.member_id, with_for_update=True, populate_existing=True)
    trainer = await session.get(OrganizationMember, data.trainer_member_id)
    if member is None or member.organization_id != org_id or member.role != Role.MEMBER:
        raise HTTPException(status_code=404, detail="Member not found in this gym.")
    if member.member_status != MemberStatus.ACTIVE or member.banned:
        raise HTTPException(status_code=409, detail="Only active members can receive training credits.")
    if trainer is None or trainer.organization_id != org_id or trainer.role != Role.TRAINER or trainer.banned:
        raise HTTPException(status_code=404, detail="Trainer not found in this gym.")
    trainer_user = await session.get(User, trainer.user_id)
    if trainer_user is None or not trainer_user.is_active:
        raise HTTPException(status_code=404, detail="Trainer not found in this gym.")

    expires = data.expires_at
    if expires and expires <= now_utc():
        raise HTTPException(status_code=422, detail="Credit expiry must be in the future.")
    assignment = (await session.execute(select(MemberTrainer).where(
        MemberTrainer.organization_id == org_id,
        MemberTrainer.member_id == member.id,
        MemberTrainer.trainer_member_id == trainer.id,
        MemberTrainer.active.is_(True),
    ))).scalar_one_or_none()
    if assignment is None:
        session.add(MemberTrainer(organization_id=org_id, member_id=member.id,
                                  trainer_member_id=trainer.id, assigned_by=actor_id))

    package = TrainerPackage(
        organization_id=org_id, member_id=member.id, trainer_member_id=trainer.id,
        granted_by_user_id=actor_id, name=data.name, total_sessions=data.total_sessions,
        expires_at=expires,
    )
    session.add(package)
    await session.flush()
    await record_audit(session, action="trainer.package_granted", organization_id=org_id,
                       actor_user_id=actor_id, entity_type="trainer_package", entity_id=package.id,
                       metadata={"member_id": member.id, "trainer_member_id": trainer.id,
                                 "sessions": package.total_sessions})
    return package


async def cancel_package(session: AsyncSession, *, org_id: str, package_id: str, actor_id: str) -> None:
    package = await session.get(TrainerPackage, package_id, with_for_update=True, populate_existing=True)
    if package is None or package.organization_id != org_id:
        raise HTTPException(status_code=404, detail="Training package not found.")
    if package.cancelled_at:
        return
    package.cancelled_at = now_utc()
    session.add(package)
    await record_audit(session, action="trainer.package_cancelled", organization_id=org_id,
                       actor_user_id=actor_id, entity_type="trainer_package", entity_id=package.id,
                       metadata={"unused_sessions": package.total_sessions - package.used_sessions})


async def list_packages(session: AsyncSession, *, org_id: str,
                        trainer_member_id: str | None = None) -> list[dict]:
    Member = aliased(OrganizationMember)
    Trainer = aliased(OrganizationMember)
    MemberUser = aliased(User)
    TrainerUser = aliased(User)
    stmt = (select(TrainerPackage, Member, MemberUser, Trainer, TrainerUser)
            .join(Member, Member.id == TrainerPackage.member_id)
            .join(MemberUser, MemberUser.id == Member.user_id)
            .join(Trainer, Trainer.id == TrainerPackage.trainer_member_id)
            .join(TrainerUser, TrainerUser.id == Trainer.user_id)
            .where(TrainerPackage.organization_id == org_id,
                   Member.organization_id == org_id, Trainer.organization_id == org_id))
    if trainer_member_id:
        stmt = stmt.where(TrainerPackage.trainer_member_id == trainer_member_id)
    # shortcut: newest 500 bundles, add pagination when gyms need older history here.
    rows = (await session.execute(stmt.order_by(TrainerPackage.created_at.desc()).limit(500))).all()
    return [{"id": package.id, "member_id": member.id,
             "member_name": member.display_name or member_user.full_name or member_user.email,
             "trainer_member_id": trainer.id,
             "trainer_name": trainer_user.full_name or trainer_user.email,
             "name": package.name, "total_sessions": package.total_sessions,
             "used_sessions": package.used_sessions,
             "remaining_sessions": max(0, package.total_sessions - package.used_sessions),
             "expires_at": package.expires_at,
             "status": "cancelled" if package.cancelled_at else
                       "expired" if package.expires_at and package.expires_at <= now_utc() else
                       "complete" if package.used_sessions >= package.total_sessions else "active"}
            for package, member, member_user, trainer, trainer_user in rows]


async def consume_package(session: AsyncSession, *, org_id: str, package_id: str,
                          trainer_member_id: str, member_id: str, actor_id: str | None = None) -> TrainerPackage:
    package = await session.get(TrainerPackage, package_id, with_for_update=True, populate_existing=True)
    if (package is None or package.organization_id != org_id or package.member_id != member_id
            or package.trainer_member_id != trainer_member_id):
        raise HTTPException(status_code=404, detail="Training package not found for this client.")
    if package.cancelled_at or (package.expires_at and package.expires_at <= now_utc()):
        raise HTTPException(status_code=409, detail="This training package has expired or was cancelled.")
    if package.used_sessions >= package.total_sessions:
        raise HTTPException(status_code=409, detail="This training package has no sessions remaining.")
    package.used_sessions += 1
    session.add(package)
    await record_audit(session, action="trainer.package_session_used", organization_id=org_id,
                       actor_user_id=actor_id,
                       entity_type="trainer_package", entity_id=package.id,
                       metadata={"member_id": member_id, "remaining": package.total_sessions - package.used_sessions})
    return package
