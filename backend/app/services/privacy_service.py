"""Tenant-scoped member privacy actions that preserve financial evidence."""

from __future__ import annotations

import secrets
from fastapi import HTTPException

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.constants import MemberStatus, Role, SubscriptionStatus
from app.core.security import hash_password, now_utc
from app.models.membership import OrganizationMember
from app.models.staff import Task
from app.models.session import AuthSession
from app.models.subscription import Subscription
from app.models.user import User
from app.models.trainer_package import TrainerPackage
from app.models.trainer_session import TrainerSessionLog
from app.services.audit_service import record_audit


async def has_shared_identity(session: AsyncSession, *, org_id: str, user_id: str) -> bool:
    count = await session.execute(
        select(func.count()).select_from(OrganizationMember).where(
            OrganizationMember.user_id == user_id,
            OrganizationMember.organization_id != org_id,
        )
    )
    return bool(count.scalar_one())


async def erase_member_from_workspace(
    session: AsyncSession, *, org_id: str, member: OrganizationMember, user: User, actor_id: str,
) -> None:
    """Redact tenant profile data and revoke access while retaining ledger rows."""
    if member.organization_id != org_id or member.user_id != user.id:
        raise HTTPException(status_code=404, detail="Member not found.")
    if member.role != Role.MEMBER:
        raise HTTPException(status_code=409, detail="Staff accounts require a separate access and employment-record review.")
    member.banned = True
    member.member_status = MemberStatus.BANNED
    member.display_name = "Erased member"
    member.phone = None
    member.photo_url = None
    member.emergency_contact = None
    member.goals = None
    member.tags = []
    member.health_notes = None
    member.id_document_type = None
    member.id_document_last4 = None
    member.profile_complete = False
    member.stripe_customer_id = None
    member.stripe_default_payment_method_id = None
    member.stripe_default_payment_method_type = None
    member.recurring_consent_at = None
    member.stripe_recurring_setup_intent_id = None
    member.marketing_email_consent = False
    member.marketing_email_consent_at = now_utc()
    member.marketing_sms_consent = False
    member.marketing_sms_consent_at = now_utc()
    member.marketing_whatsapp_consent = False
    member.marketing_whatsapp_consent_at = now_utc()
    member.marketing_in_app_consent = False
    member.marketing_in_app_consent_at = now_utc()
    session.add(member)

    cases = (await session.execute(select(Task).where(
        Task.organization_id == org_id, Task.related_member_id == member.id, Task.category == "retention",
    ))).scalars().all()
    for task in cases:
        task.title = "Retention case — erased member"
        task.description = None
        task.done = True
        task.case_outcome = "cancelled"
        session.add(task)

    packages = (await session.execute(select(TrainerPackage).where(
        TrainerPackage.organization_id == org_id, TrainerPackage.member_id == member.id,
    ).with_for_update())).scalars().all()
    for package in packages:
        package.name = "Erased member training credits"
        package.cancelled_at = package.cancelled_at or now_utc()
        session.add(package)
    training_logs = (await session.execute(select(TrainerSessionLog).where(
        TrainerSessionLog.organization_id == org_id, TrainerSessionLog.client_member_id == member.id,
    ))).scalars().all()
    for log in training_logs:
        log.focus = "Erased member training session"
        log.notes = ""
        session.add(log)

    subscriptions = (await session.execute(select(Subscription).where(
        Subscription.organization_id == org_id, Subscription.member_id == member.id,
    ))).scalars().all()
    for subscription in subscriptions:
        if subscription.status in {SubscriptionStatus.ACTIVE, SubscriptionStatus.GRACE, SubscriptionStatus.FROZEN}:
            subscription.status = SubscriptionStatus.CANCELLED
        subscription.auto_renew = False
        subscription.next_renewal_attempt_at = None
        session.add(subscription)

    sessions = (await session.execute(select(AuthSession).where(
        AuthSession.user_id == user.id, AuthSession.organization_id == org_id,
        AuthSession.revoked.is_(False),
    ))).scalars().all()
    for auth_session in sessions:
        auth_session.revoked = True
        auth_session.revoked_at = now_utc()
        session.add(auth_session)

    shared_identity_preserved = await has_shared_identity(session, org_id=org_id, user_id=user.id)
    if not shared_identity_preserved:
        user.email = f"erased-{user.id}@privacy.invalid"
        user.full_name = None
        user.phone = None
        user.address = None
        user.city = None
        user.occupation = None
        user.education = None
        user.date_of_birth = None
        user.gender = None
        user.emergency_contact = None
        user.cnic = None
        user.email_verified = False
        user.is_active = False
        user.hashed_password = hash_password(secrets.token_urlsafe(32))
        user.mfa_enabled = False
        user.mfa_secret = None
        user.last_org_id = None
        session.add(user)

    await record_audit(
        session, action="privacy.member_profile_redacted", organization_id=org_id,
        actor_user_id=actor_id, entity_type="member", entity_id=member.id,
        metadata={"ledger_retained": True, "shared_identity_preserved": shared_identity_preserved},
    )
