"""Member referral codes, paid conversions, and reward fulfillment."""

from __future__ import annotations

import secrets
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.constants import EnrollmentMode, MemberStatus
from app.core.security import now_utc
from app.models.lead import Lead
from app.models.membership import OrganizationMember
from app.models.organization import Organization
from app.models.referral import Referral, ReferralCode, ReferralProgram, ReferralReward
from app.models.user import User
from app.schemas.referrals import ReferralProgramUpdate
from app.services.audit_service import record_audit
from app.services.leads_service import change_stage


async def program_for_org(session: AsyncSession, *, org_id: str) -> ReferralProgram | None:
    return (await session.execute(
        select(ReferralProgram).where(ReferralProgram.organization_id == org_id)
    )).scalar_one_or_none()


async def set_program(session: AsyncSession, *, org_id: str, actor_id: str,
                      data: ReferralProgramUpdate) -> ReferralProgram:
    organization = await session.get(Organization, org_id)
    if data.enabled and organization is not None and (
        organization.industry == "office"
        or organization.enrollment_mode == EnrollmentMode.INVITE_ONLY
    ):
        raise HTTPException(
            status_code=400,
            detail="Referral codes require open or approved member enrollment.",
        )
    program = await program_for_org(session, org_id=org_id)
    if program is None:
        program = ReferralProgram(organization_id=org_id, updated_by=actor_id,
                                  enabled=data.enabled, reward_description=data.reward_description.strip(),
                                  reward_amount_minor=int(data.reward_amount * 100),
                                  reward_currency=organization.default_currency.upper() if organization else "USD")
    else:
        program.enabled = data.enabled
        program.reward_description = data.reward_description.strip()
        program.reward_amount_minor = int(data.reward_amount * 100)
        program.reward_currency = organization.default_currency.upper() if organization else program.reward_currency
        program.updated_by = actor_id
        program.updated_at = now_utc()
    session.add(program)
    await session.flush()
    await record_audit(session, action="referral.program_updated", organization_id=org_id,
                       actor_user_id=actor_id, entity_type="referral_program", entity_id=program.id,
                       new_values={"enabled": program.enabled,
                                   "reward_description": program.reward_description,
                                   "reward_amount_minor": program.reward_amount_minor,
                                   "reward_currency": program.reward_currency})
    return program


async def validate_code(session: AsyncSession, *, org_id: str, code: str) -> ReferralCode:
    program = await program_for_org(session, org_id=org_id)
    if program is None or not program.enabled:
        raise HTTPException(status_code=400, detail="This organization is not running a referral program.")
    referral_code = (await session.execute(
        select(ReferralCode).where(
            ReferralCode.organization_id == org_id,
            ReferralCode.code == code.strip().upper(),
        )
    )).scalar_one_or_none()
    if referral_code is None:
        raise HTTPException(status_code=400, detail="Referral code not found.")
    referrer = await session.get(OrganizationMember, referral_code.member_id)
    if referrer is None or referrer.organization_id != org_id or referrer.member_status != MemberStatus.ACTIVE:
        raise HTTPException(status_code=400, detail="Referral code is no longer active.")
    return referral_code


async def attach_referral(session: AsyncSession, *, org_id: str, member_id: str,
                          referral_code: ReferralCode) -> Referral:
    program = await program_for_org(session, org_id=org_id)
    row = Referral(
        organization_id=org_id,
        referral_code_id=referral_code.id,
        referrer_member_id=referral_code.member_id,
        referred_member_id=member_id,
        reward_description=program.reward_description if program else "Referral reward",
        status="pending",
    )
    session.add(row)
    await session.flush()
    return row


async def qualify_referral_for_member(
    session: AsyncSession, *, org_id: str, member_id: str,
) -> Referral | None:
    referral = (await session.execute(
        select(Referral).where(
            Referral.organization_id == org_id,
            Referral.referred_member_id == member_id,
        )
    )).scalar_one_or_none()
    if referral is None or referral.status == "qualified":
        return referral

    referral.status = "qualified"
    referral.qualified_at = now_utc()
    session.add(referral)
    program = await program_for_org(session, org_id=org_id)
    for recipient_id in {referral.referrer_member_id, referral.referred_member_id}:
        reward = ReferralReward(
            organization_id=org_id,
            referral_id=referral.id,
            recipient_member_id=recipient_id,
            description=referral.reward_description,
            amount_minor=program.reward_amount_minor if program else 0,
            currency=program.reward_currency if program else "USD",
        )
        session.add(reward)

    member = await session.get(OrganizationMember, member_id)
    user = await session.get(User, member.user_id) if member else None
    if user is not None:
        lead = (await session.execute(
            select(Lead).where(
                Lead.organization_id == org_id,
                Lead.email == user.email.lower(),
            ).order_by(Lead.created_at.desc())
        )).scalars().first()
        created = lead is None
        if created:
            lead = Lead(
                organization_id=org_id,
                name=user.full_name or user.email.split("@", 1)[0],
                email=user.email,
                phone=member.phone if member else None,
                source="referral",
                stage="joined",
                created_by=user.id,
                converted_member_id=member_id,
                referred_by_member_id=referral.referrer_member_id,
            )
        else:
            if lead.source == "staff_entered":
                lead.source = "referral"
            lead.converted_member_id = member_id
            lead.referred_by_member_id = referral.referrer_member_id
            lead.updated_at = now_utc()
        session.add(lead)
        await change_stage(session, lead=lead, stage="joined", actor_id=user.id,
                           origin="referral", created=created)

    await record_audit(session, action="referral.qualified", organization_id=org_id,
                       actor_user_id=user.id if user else None,
                       entity_type="referral", entity_id=referral.id,
                       metadata={"referrer_member_id": referral.referrer_member_id,
                                 "referred_member_id": referral.referred_member_id})
    return referral


async def _ensure_code(session: AsyncSession, *, org_id: str, member_id: str) -> ReferralCode:
    code = (await session.execute(
        select(ReferralCode).where(
            ReferralCode.organization_id == org_id,
            ReferralCode.member_id == member_id,
        )
    )).scalar_one_or_none()
    if code is not None:
        return code
    code = ReferralCode(organization_id=org_id, member_id=member_id,
                        code=f"ACR{secrets.token_hex(4).upper()}")
    session.add(code)
    await session.flush()
    return code


async def member_overview(session: AsyncSession, *, org_id: str, user_id: str) -> dict:
    member = (await session.execute(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == org_id,
            OrganizationMember.user_id == user_id,
        )
    )).scalar_one_or_none()
    if member is None or member.role.value != "member":
        raise HTTPException(status_code=404, detail="Member profile not found.")
    program = await program_for_org(session, org_id=org_id)
    organization = await session.get(Organization, org_id)
    code = None
    if (
        program is not None
        and program.enabled
        and member.member_status == MemberStatus.ACTIVE
        and organization is not None
        and organization.industry != "office"
        and organization.enrollment_mode != EnrollmentMode.INVITE_ONLY
    ):
        code = (await _ensure_code(session, org_id=org_id, member_id=member.id)).code

    rows = (await session.execute(
        select(Referral, OrganizationMember, User)
        .join(OrganizationMember, OrganizationMember.id == Referral.referred_member_id)
        .join(User, User.id == OrganizationMember.user_id)
        .where(Referral.organization_id == org_id,
               Referral.referrer_member_id == member.id)
        .order_by(Referral.created_at.desc())
    )).all()
    rewards = (await session.execute(
        select(ReferralReward).where(
            ReferralReward.organization_id == org_id,
            ReferralReward.recipient_member_id == member.id,
        ).order_by(ReferralReward.earned_at.desc())
    )).scalars().all()
    return {
        "enabled": bool(program and program.enabled),
        "code": code,
        "organization_code": organization.org_code if organization else "",
        "reward_description": program.reward_description if program else "A referral reward",
        "referrals": [{
            "id": referral.id,
            "referred_name": referred.display_name or user.full_name or user.email,
            "status": referral.status,
            "reward_description": referral.reward_description,
            "created_at": referral.created_at,
        } for referral, referred, user in rows],
        "earned_rewards": [{
            "id": reward.id,
            "description": reward.description,
            "status": reward.status,
            "earned_at": reward.earned_at,
            "fulfilled_at": reward.fulfilled_at,
        } for reward in rewards],
    }


async def admin_overview(session: AsyncSession, *, org_id: str, program: ReferralProgram | None) -> dict:
    rows = (await session.execute(
        select(Referral, OrganizationMember, User)
        .join(OrganizationMember, OrganizationMember.id == Referral.referrer_member_id)
        .join(User, User.id == OrganizationMember.user_id)
        .where(Referral.organization_id == org_id)
        .order_by(Referral.created_at.desc())
    )).all()
    result = []
    pending_rewards = 0
    qualified_count = 0
    for referral, referrer, referrer_user in rows:
        referred = await session.get(OrganizationMember, referral.referred_member_id)
        referred_user = await session.get(User, referred.user_id) if referred else None
        reward_rows = (await session.execute(
            select(ReferralReward).where(ReferralReward.referral_id == referral.id)
        )).scalars().all()
        pending_rewards += sum(reward.status == "earned" for reward in reward_rows)
        qualified_count += referral.status == "qualified"
        result.append({
            "id": referral.id,
            "referrer_name": referrer.display_name or referrer_user.full_name or referrer_user.email,
            "referrer_email": referrer_user.email,
            "referred_name": (referred.display_name if referred else None)
                             or (referred_user.full_name if referred_user else None)
                             or (referred_user.email if referred_user else "Pending signup"),
            "referred_email": referred_user.email if referred_user else "",
            "status": referral.status,
            "reward_description": referral.reward_description,
            "qualified_at": referral.qualified_at,
            "rewards": [{"id": reward.id, "recipient_member_id": reward.recipient_member_id,
                         "description": reward.description, "status": reward.status,
                         "amount_minor": reward.amount_minor, "currency": reward.currency}
                        for reward in reward_rows],
        })
    return {
        "program": {
            "enabled": bool(program and program.enabled),
            "reward_description": program.reward_description if program else "A referral reward",
            "reward_amount": Decimal(program.reward_amount_minor if program else 0) / 100,
            "reward_currency": program.reward_currency if program else "USD",
        },
        "referrals": result,
        "pending_rewards": pending_rewards,
        "qualified_count": qualified_count,
    }


async def fulfill_reward(session: AsyncSession, *, org_id: str, reward_id: str,
                         actor_id: str) -> ReferralReward:
    reward = await session.get(ReferralReward, reward_id, with_for_update=True)
    if reward is None or reward.organization_id != org_id:
        raise HTTPException(status_code=404, detail="Referral reward not found.")
    if reward.status == "fulfilled":
        raise HTTPException(status_code=409, detail="Referral reward has already been fulfilled.")
    if reward.amount_minor > 0:
        from app.services.member_vault_service import post

        await post(
            session, org_id=org_id, member_id=reward.recipient_member_id,
            currency=reward.currency, amount=reward.amount_minor,
            reference=f"referral-reward:{reward.id}", description=reward.description,
        )
    reward.status = "fulfilled"
    reward.fulfilled_at = now_utc()
    reward.fulfilled_by = actor_id
    session.add(reward)
    await record_audit(session, action="referral.reward_fulfilled", organization_id=org_id,
                       actor_user_id=actor_id, entity_type="referral_reward", entity_id=reward.id,
                       new_values={"description": reward.description},
                       metadata={"amount_minor": reward.amount_minor, "currency": reward.currency})
    return reward
