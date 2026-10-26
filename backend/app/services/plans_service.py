"""Membership plan builder & lifecycle (Section 6).

Plans are owner-defined. Key rules enforced here:
  * Drafts never appear in member signup (Section 6.1).
  * Publishing the first plan flips the org checklist flag that unblocks member
    signup (Section 6 critical constraint).
  * Editing price does NOT reprice existing members — that is preserved by
    snapshotting price onto Subscription at signup (see memberships_service).
  * Archive hides the plan everywhere and records a replacement plan for
    migrating existing members at next renewal (Section 6.7).
"""

from __future__ import annotations

import json
import re

from fastapi import HTTPException
from jsonschema import ValidationError as JsonSchemaError
from jsonschema import validate as json_schema_validate
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func
from sqlmodel import select

from app.core.constants import PlanBillingType, PlanStatus, PlanVisibility, SubscriptionStatus
from app.core.industry import OfferKind, get_industry
from app.models.organization import Organization
from app.models.membership import OrganizationMember
from app.models.plan import MembershipPlan
from app.models.subscription import Subscription
from app.realtime import events
from app.schemas.plans import PlanCreate, PlanUpdate
from app.services.audit_service import record_audit


def _industry_for(org: Organization):
    try:
        return get_industry(org.industry or "gym")
    except KeyError:
        return get_industry("gym")


def _validate_offer_spec(org: Organization, offer_kind: OfferKind, spec: dict) -> None:
    """Validate a non-membership offer spec against its industry JSON Schema."""

    industry = _industry_for(org)
    try:
        json_schema_validate(spec, industry.load_offer_schema())
    except JsonSchemaError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid {offer_kind.value} spec: {exc.message}",
        ) from exc


def _resolve_offer(org: Organization, data: PlanCreate) -> tuple[OfferKind, dict | None]:
    """Determine + validate the offer kind/spec for a new plan.

    The offer kind defaults to the org's industry offer kind; an explicit kind
    must match the org's vertical. space/course specs are required and validated
    against the industry JSON Schema. membership specs are optional (the classic
    membership columns stay authoritative).
    """

    industry = _industry_for(org)

    offer_kind = data.offer_kind or industry.offer_kind
    if offer_kind is not industry.offer_kind:
        raise HTTPException(
            status_code=422,
            detail=f"Org industry '{industry.key_value}' only supports "
                   f"{industry.offer_kind.value} offers (got {offer_kind.value}).",
        )

    spec = data.spec
    if offer_kind is OfferKind.MEMBERSHIP:
        return offer_kind, spec

    if spec is None:
        raise HTTPException(
            status_code=422,
            detail=f"An {offer_kind.value} offer requires an industry spec.",
        )
    _validate_offer_spec(org, offer_kind, spec)
    return offer_kind, spec


def _validate_membership_variant(plan: MembershipPlan) -> None:
    """Keep plan limits coherent before a draft is saved or published."""
    if not isinstance(plan.billing_type, PlanBillingType):
        raise HTTPException(status_code=422, detail="Choose a valid billing type.")
    if plan.offer_kind != "membership":
        if any((plan.family_capacity, plan.included_credits, plan.off_peak_start, plan.off_peak_end)) or plan.audience != "standard":
            raise HTTPException(status_code=422, detail="Membership variants are only available for membership plans.")
        return
    if plan.audience not in {"standard", "student", "family"}:
        raise HTTPException(status_code=422, detail="Audience must be standard, student, or family.")
    if (plan.audience == "family") != (plan.family_capacity is not None):
        raise HTTPException(status_code=422, detail="Family plans require a capacity; other plans cannot set one.")
    if plan.family_capacity is not None and not 2 <= plan.family_capacity <= 20:
        raise HTTPException(status_code=422, detail="Family capacity must be between 2 and 20.")
    if bool(plan.off_peak_start) != bool(plan.off_peak_end):
        raise HTTPException(status_code=422, detail="Provide both off-peak start and end times.")
    for value in (plan.off_peak_start, plan.off_peak_end):
        if value and (not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value)):
            raise HTTPException(status_code=422, detail="Off-peak times must use 24-hour HH:MM format.")
    if plan.off_peak_start and plan.off_peak_start == plan.off_peak_end:
        raise HTTPException(status_code=422, detail="Off-peak start and end cannot be the same.")
    if plan.billing_type.value == "recurring":
        if plan.cycle_length is None:
            plan.cycle_length = 1
        if plan.cycle_unit is None:
            plan.cycle_unit = "month"
        if not plan.cycle_length or not 1 <= plan.cycle_length <= 365:
            raise HTTPException(status_code=422, detail="Recurring plans need a cycle length from 1 to 365.")
        if plan.cycle_unit not in {"day", "week", "month", "year"}:
            raise HTTPException(status_code=422, detail="Recurring cycle unit must be day, week, month, or year.")
    if plan.billing_type.value == "one_time_pack" and (not plan.pack_size or plan.pack_size < 1):
        raise HTTPException(status_code=422, detail="Class packs need at least one class credit.")
    if plan.included_credits is not None and (plan.included_credits < 1 or plan.billing_type.value != "recurring"):
        raise HTTPException(status_code=422, detail="Included credits require a recurring plan and a positive allowance.")
    if plan.validity_days is not None and plan.validity_days < 1:
        raise HTTPException(status_code=422, detail="Pack validity must be positive.")


async def create_plan(
    session: AsyncSession, *, org: Organization, data: PlanCreate, actor_id: str
) -> MembershipPlan:
    offer_kind, spec = _resolve_offer(org, data)
    plan = MembershipPlan(
        organization_id=org.id,
        name=data.name,
        public_description=data.public_description,
        internal_notes=data.internal_notes,
        price=data.price,
        joining_fee=data.joining_fee,
        currency=data.currency or org.default_currency,
        tax_mode=data.tax_mode,
        tax_rate=data.tax_rate,
        billing_type=data.billing_type,
        cycle_length=data.cycle_length,
        cycle_unit=data.cycle_unit,
        auto_renew=data.auto_renew,
        trial_days=data.trial_days,
        pack_size=data.pack_size,
        validity_days=data.validity_days,
        audience=data.audience,
        family_capacity=data.family_capacity,
        off_peak_start=data.off_peak_start,
        off_peak_end=data.off_peak_end,
        included_credits=data.included_credits,
        inclusions_json=data.inclusions_json,
        rules_json=data.rules_json,
        visibility=data.visibility,
        featured=data.featured,
        status=PlanStatus.DRAFT,
        offer_kind=offer_kind.value,
        org_industry=org.industry or "gym",
        spec_json=json.dumps(spec) if spec is not None else None,
    )
    _validate_membership_variant(plan)

    session.add(plan)
    await session.flush()
    await record_audit(session, action="plan.created", organization_id=org.id, actor_user_id=actor_id,
                       entity_type="plan", entity_id=plan.id,
                       new_values={"name": plan.name, "offer_kind": plan.offer_kind})
    await events.plan_changed(org.id, plan_id=plan.id, action="created")
    return plan


async def get_owned_plan(session: AsyncSession, org_id: str, plan_id: str) -> MembershipPlan:
    plan = await session.get(MembershipPlan, plan_id)
    if plan is None or plan.organization_id != org_id:
        raise HTTPException(status_code=404, detail="Plan not found.")
    return plan


async def update_plan(
    session: AsyncSession, *, org_id: str, plan_id: str, data: PlanUpdate, actor_id: str
) -> MembershipPlan:
    plan = await get_owned_plan(session, org_id, plan_id)
    old_price = plan.price
    updates = data.model_dump(exclude_unset=True)
    # offer_kind/spec are not columns on the model directly; they map onto
    # `offer_kind` + `spec_json`, so pull them out before the generic setattr.
    spec = updates.pop("spec", None)
    offer_kind = updates.pop("offer_kind", None)
    for field, value in updates.items():
        setattr(plan, field, value)

    if offer_kind is not None:
        plan.offer_kind = offer_kind.value if isinstance(offer_kind, OfferKind) else str(offer_kind)

    if spec is not None:
        kind = OfferKind(plan.offer_kind or "membership")
        if kind is OfferKind.MEMBERSHIP:
            plan.spec_json = json.dumps(spec) if spec else None
        else:
            org = await session.get(Organization, org_id)
            _validate_offer_spec(org, kind, spec)
            plan.spec_json = json.dumps(spec)

    _validate_membership_variant(plan)

    # Existing households must keep enough places after an owner edits a plan.
    active_owners = (await session.execute(
        select(Subscription.member_id).where(
            Subscription.organization_id == org_id,
            Subscription.plan_id == plan.id,
            Subscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.GRACE]),
        )
    )).scalars().all()
    for owner_id in set(active_owners):
        linked = (await session.execute(
            select(func.count()).select_from(OrganizationMember).where(
                OrganizationMember.organization_id == org_id,
                OrganizationMember.family_owner_member_id == owner_id,
                OrganizationMember.family_billing_mode == "shared_plan",
            )
        )).scalar_one()
        if linked and (plan.audience != "family" or not plan.family_capacity or linked + 1 > plan.family_capacity):
            raise HTTPException(status_code=422, detail="This plan already covers family members; keep its family capacity.")

    session.add(plan)
    await record_audit(
        session, action="plan.updated", organization_id=org_id, actor_user_id=actor_id,
        entity_type="plan", entity_id=plan.id,
        old_values={"price": old_price}, new_values={"price": plan.price},
        metadata={"note": "existing members keep snapshot price"},
    )
    await events.plan_changed(org_id, plan_id=plan.id, action="updated")
    return plan


async def publish_plan(
    session: AsyncSession, *, org: Organization, plan_id: str, actor_id: str
) -> MembershipPlan:
    plan = await get_owned_plan(session, org.id, plan_id)
    _validate_membership_variant(plan)
    plan.status = PlanStatus.PUBLISHED
    session.add(plan)
    # Unblock member signup once at least one plan is published.
    if not org.checklist_plan_published:
        org.checklist_plan_published = True
        session.add(org)
    await record_audit(session, action="plan.published", organization_id=org.id, actor_user_id=actor_id,
                       entity_type="plan", entity_id=plan.id)
    await events.plan_changed(org.id, plan_id=plan.id, action="published")
    return plan


async def set_status(
    session: AsyncSession, *, org_id: str, plan_id: str, status: PlanStatus, actor_id: str
) -> MembershipPlan:
    plan = await get_owned_plan(session, org_id, plan_id)
    plan.status = status
    session.add(plan)
    await record_audit(session, action=f"plan.{status.value}", organization_id=org_id,
                       actor_user_id=actor_id, entity_type="plan", entity_id=plan.id)
    await events.plan_changed(org_id, plan_id=plan.id, action=status.value)
    return plan


async def archive_plan(
    session: AsyncSession, *, org_id: str, plan_id: str, replacement_plan_id: str | None, actor_id: str
) -> MembershipPlan:
    plan = await get_owned_plan(session, org_id, plan_id)
    if replacement_plan_id:
        await get_owned_plan(session, org_id, replacement_plan_id)  # validate ownership
        plan.replacement_plan_id = replacement_plan_id
    plan.status = PlanStatus.ARCHIVED
    session.add(plan)
    await record_audit(session, action="plan.archived", organization_id=org_id, actor_user_id=actor_id,
                       entity_type="plan", entity_id=plan.id,
                       metadata={"replacement_plan_id": replacement_plan_id})
    await events.plan_changed(org_id, plan_id=plan.id, action="archived")
    return plan


async def unarchive_plan(
    session: AsyncSession, *, org_id: str, plan_id: str, actor_id: str
) -> MembershipPlan:
    plan = await get_owned_plan(session, org_id, plan_id)
    plan.status = PlanStatus.DRAFT
    plan.replacement_plan_id = None
    session.add(plan)
    await record_audit(session, action="plan.unarchived", organization_id=org_id, actor_user_id=actor_id,
                       entity_type="plan", entity_id=plan.id)
    await events.plan_changed(org_id, plan_id=plan.id, action="unarchived")
    return plan


async def delete_plan(
    session: AsyncSession, *, org_id: str, plan_id: str, actor_id: str
) -> None:
    plan = await get_owned_plan(session, org_id, plan_id)
    active = (
        await session.execute(
            select(Subscription).where(
                Subscription.plan_id == plan_id,
                Subscription.status.in_([
                    SubscriptionStatus.ACTIVE, SubscriptionStatus.GRACE,
                    SubscriptionStatus.FROZEN,
                ]),
            )
        )
    ).scalars().first()
    if active is not None:
        raise HTTPException(
            status_code=409,
            detail="Cannot delete a plan that has active members. Archive it instead.",
        )
    await record_audit(session, action="plan.deleted", organization_id=org_id, actor_user_id=actor_id,
                       entity_type="plan", entity_id=plan.id,
                       old_values={"name": plan.name, "status": plan.status.value})
    await session.delete(plan)
    await events.plan_changed(org_id, plan_id=plan_id, action="deleted")


async def duplicate_plan(
    session: AsyncSession, *, org_id: str, plan_id: str, actor_id: str
) -> MembershipPlan:
    src = await get_owned_plan(session, org_id, plan_id)
    copy = MembershipPlan(
        **{
            k: v for k, v in src.model_dump().items()
            if k not in {"id", "created_at", "updated_at", "status", "name", "replacement_plan_id"}
        },
        name=f"{src.name} (copy)",
        status=PlanStatus.DRAFT,
    )
    session.add(copy)
    await session.flush()
    await record_audit(session, action="plan.duplicated", organization_id=org_id, actor_user_id=actor_id,
                       entity_type="plan", entity_id=copy.id, metadata={"source": plan_id})
    await events.plan_changed(org_id, plan_id=copy.id, action="duplicated")
    return copy


async def list_plans(
    session: AsyncSession, *, org_id: str, offer_kind: OfferKind | None = None
) -> list[MembershipPlan]:
    query = select(MembershipPlan).where(MembershipPlan.organization_id == org_id)
    if offer_kind is not None:
        query = query.where(MembershipPlan.offer_kind == offer_kind.value)
    return list((await session.execute(query)).scalars())


async def list_public_plans(session: AsyncSession, *, org_id: str) -> list[MembershipPlan]:
    """Plans a prospective member can see at signup (published + public)."""

    return list(
        (
            await session.execute(
                select(MembershipPlan).where(
                    MembershipPlan.organization_id == org_id,
                    MembershipPlan.status == PlanStatus.PUBLISHED,
                    MembershipPlan.visibility == PlanVisibility.PUBLIC,
                )
            )
        ).scalars()
    )
