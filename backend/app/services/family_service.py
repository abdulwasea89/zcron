"""Organization-scoped family-plan membership and shared entitlement lookup."""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.constants import MemberStatus, Role, SubscriptionStatus
from app.models.membership import OrganizationMember
from app.models.plan import MembershipPlan
from app.models.subscription import Subscription
from app.core.security import now_utc
from app.realtime import events
from app.services.audit_service import record_audit


async def latest_subscription(session: AsyncSession, org_id: str, member_id: str) -> Subscription | None:
    return (await session.execute(
        select(Subscription).where(
            Subscription.organization_id == org_id, Subscription.member_id == member_id,
        ).order_by(Subscription.created_at.desc())
    )).scalars().first()


async def covered_subscription(
    session: AsyncSession, org_id: str, member: OrganizationMember,
) -> Subscription | None:
    shared = member.family_owner_member_id and member.family_billing_mode == "shared_plan"
    payer_id = member.family_owner_member_id if shared else member.id
    sub = await latest_subscription(session, org_id, payer_id)
    if sub is None or sub.status not in {SubscriptionStatus.ACTIVE, SubscriptionStatus.GRACE}:
        return None
    if shared:
        plan = await session.get(MembershipPlan, sub.plan_id)
        if plan is None or plan.organization_id != org_id or plan.audience != "family":
            return None
    return sub


async def family_members(session: AsyncSession, org_id: str, owner_id: str) -> list[OrganizationMember]:
    return list((await session.execute(select(OrganizationMember).where(
        OrganizationMember.organization_id == org_id,
        OrganizationMember.family_owner_member_id == owner_id,
    ))).scalars())


async def sync_family_status(
    session: AsyncSession, org_id: str, owner_id: str, status: MemberStatus,
) -> None:
    """Keep covered members' roster state aligned with the payer's lifecycle."""
    for dependent in await family_members(session, org_id, owner_id):
        if dependent.family_billing_mode != "shared_plan":
            continue
        if dependent.banned or dependent.member_status in {MemberStatus.BANNED, MemberStatus.CANCELLED}:
            continue
        if status == MemberStatus.ACTIVE and dependent.member_status in {MemberStatus.EXPIRED, MemberStatus.GRACE, MemberStatus.FROZEN}:
            dependent.member_status = MemberStatus.ACTIVE
        elif status != MemberStatus.ACTIVE and dependent.member_status in {MemberStatus.ACTIVE, MemberStatus.GRACE}:
            dependent.member_status = MemberStatus.FROZEN if status == MemberStatus.FROZEN else MemberStatus.EXPIRED
        else:
            continue
        session.add(dependent)
        await events.membership_changed(org_id, member_id=dependent.id, status=dependent.member_status.value)


async def set_family_member(
    session: AsyncSession, *, org_id: str, owner_id: str, dependent_id: str,
    attach: bool, actor_id: str, billing_mode: str = "shared_plan",
) -> None:
    if billing_mode not in {"shared_plan", "independent"}:
        raise HTTPException(status_code=422, detail="Choose shared-plan coverage or independent billing.")
    # Lock the two members in stable order to avoid competing link operations.
    rows = (await session.execute(select(OrganizationMember).where(
        OrganizationMember.organization_id == org_id, OrganizationMember.id.in_([owner_id, dependent_id]),
    ).order_by(OrganizationMember.id).with_for_update())).scalars().all()
    by_id = {member.id: member for member in rows}
    owner, dependent = by_id.get(owner_id), by_id.get(dependent_id)
    if (owner is None or dependent is None or owner.organization_id != org_id
            or dependent.organization_id != org_id):
        raise HTTPException(status_code=404, detail="Member not found in this organization.")
    if owner.id == dependent.id or owner.role != Role.MEMBER or dependent.role != Role.MEMBER:
        raise HTTPException(status_code=422, detail="Family links require two distinct members.")
    if attach and (owner.banned or owner.member_status not in {MemberStatus.ACTIVE, MemberStatus.GRACE}
                   or dependent.banned or dependent.member_status in {MemberStatus.PENDING_APPROVAL, MemberStatus.PENDING_ACTIVATION}):
        raise HTTPException(status_code=422, detail="This member cannot be added until approved and active.")
    if attach:
        if dependent.family_owner_member_id and dependent.family_owner_member_id != owner.id:
            raise HTTPException(status_code=409, detail="Member already belongs to another family plan.")
        if owner.family_owner_member_id or await family_members(session, org_id, dependent.id):
            raise HTTPException(status_code=409, detail="Nested family plans are not supported.")
        linked = await family_members(session, org_id, owner.id)
        if dependent.family_owner_member_id == owner.id:
            if dependent.family_billing_mode != billing_mode:
                raise HTTPException(status_code=409, detail="Remove the existing family link before changing its billing mode.")
            return
        if len(linked) >= 19:
            raise HTTPException(status_code=409, detail="Households support up to 20 members.")
        if billing_mode == "shared_plan":
            sub = await covered_subscription(session, org_id, owner)
            plan = await session.get(MembershipPlan, sub.plan_id) if sub else None
            if plan is None or plan.audience != "family" or not plan.family_capacity:
                raise HTTPException(status_code=422, detail="The paying member needs an active family plan.")
            valid_until = sub.grace_until if sub.status == SubscriptionStatus.GRACE and sub.grace_until else sub.current_period_end
            if valid_until and valid_until < now_utc():
                raise HTTPException(status_code=422, detail="The family plan has expired.")
            own_sub = await latest_subscription(session, org_id, dependent.id)
            if own_sub and own_sub.status in {SubscriptionStatus.ACTIVE, SubscriptionStatus.GRACE, SubscriptionStatus.FROZEN}:
                raise HTTPException(status_code=409, detail="Member already has an active plan. Use independent billing instead.")
            if sum(member.family_billing_mode == "shared_plan" for member in linked) >= plan.family_capacity - 1:
                raise HTTPException(status_code=409, detail="Family plan is at capacity.")
            dependent.member_status = MemberStatus.ACTIVE
        dependent.family_owner_member_id = owner.id
        dependent.family_billing_mode = billing_mode
    else:
        if dependent.family_owner_member_id != owner.id:
            raise HTTPException(status_code=404, detail="Member is not linked to this household.")
        if dependent.family_billing_mode == "shared_plan":
            dependent.member_status = MemberStatus.EXPIRED
        dependent.family_owner_member_id = None
        dependent.family_billing_mode = "shared_plan"
    session.add(dependent)
    await record_audit(
        session, action="member.family_linked" if attach else "member.family_unlinked",
        organization_id=org_id, actor_user_id=actor_id,
        entity_type="member", entity_id=dependent.id,
        metadata={"family_owner_member_id": owner.id, "billing_mode": billing_mode if attach else "removed"},
    )
    await events.membership_changed(org_id, member_id=dependent.id, status=dependent.member_status.value)
