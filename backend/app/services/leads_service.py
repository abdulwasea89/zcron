"""Tenant-scoped lead profile operations."""

from __future__ import annotations

import json
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.class_session import ClassSession
from app.models.lead import Lead, LeadBooking
from app.models.membership import OrganizationMember
from app.models.audit_log import AuditLog
from app.models.user import User
from app.core.security import now_utc
from app.schemas.leads import LeadCreate, LeadUpdate
from app.services.audit_service import record_audit

_PROFILE_FIELDS = {"goal", "budget", "preferred_times", "preferences"}
_STAGES = {"new", "contacted", "trial_booked", "visited", "joined", "lost"}
_ACTIVE_BOOKING_STATUS = "scheduled"
_BOOKING_STATUSES = {_ACTIVE_BOOKING_STATUS, "attended", "no_show", "cancelled"}


async def change_stage(session: AsyncSession, *, lead: Lead, stage: str,
                       actor_id: str | None, origin: str = "manual", created: bool = False) -> None:
    if stage not in _STAGES:
        raise HTTPException(status_code=422, detail="Invalid lead stage.")
    previous = None if created else lead.stage
    if previous == stage:
        return
    lead.stage = stage
    lead.updated_at = now_utc()
    session.add(lead)
    await record_audit(
        session, action="lead.stage_changed", organization_id=lead.organization_id,
        actor_user_id=actor_id, entity_type="lead", entity_id=lead.id,
        old_values={"stage": previous}, new_values={"stage": stage},
        metadata={"origin": origin, "created": created},
    )


async def stage_history(session: AsyncSession, *, org_id: str, lead_id: str,
                        page: int = 1, page_size: int = 20) -> dict:
    await get_lead(session, org_id=org_id, lead_id=lead_id)
    rows = (await session.execute(
        select(AuditLog, User.full_name).outerjoin(User, User.id == AuditLog.actor_user_id)
        .where(AuditLog.organization_id == org_id, AuditLog.entity_type == "lead",
               AuditLog.entity_id == lead_id,
               AuditLog.action.in_(["lead.stage_changed", "lead.updated"]))
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
    )).all()
    items = []
    for entry, actor_name in rows:
        new = json.loads(entry.new_values_json or "{}")
        old = json.loads(entry.old_values_json or "{}")
        metadata = json.loads(entry.metadata_json or "{}")
        if new.get("stage") not in _STAGES:
            continue
        items.append({
            "id": entry.id, "previous_stage": old.get("stage"), "stage": new["stage"],
            "actor_name": actor_name, "actor_user_id": entry.actor_user_id,
            "created_at": entry.created_at,
            "origin": metadata.get("origin", "manual"),
            "created": metadata.get("created", False),
        })
    offset = (page - 1) * page_size
    return {"items": items[offset:offset + page_size], "total": len(items),
            "page": page, "page_size": page_size}


async def list_leads(session: AsyncSession, *, org_id: str) -> list[Lead]:
    return list((await session.execute(
        select(Lead).where(Lead.organization_id == org_id).order_by(Lead.updated_at.desc())
    )).scalars())


async def get_lead(session: AsyncSession, *, org_id: str, lead_id: str) -> Lead:
    lead = await session.get(Lead, lead_id)
    if lead is None or lead.organization_id != org_id:
        raise HTTPException(status_code=404, detail="Lead not found.")
    return lead


async def _reject_duplicate_contact(
    session: AsyncSession,
    *,
    org_id: str,
    email: str | None,
    phone: str | None,
    exclude_lead_id: str | None = None,
) -> None:
    contact_matches = []
    if email:
        contact_matches.append(Lead.email == email)
    if phone:
        bare_phone = phone.lstrip("+")
        contact_matches.append(Lead.phone.in_({bare_phone, f"+{bare_phone}"}))
    if not contact_matches:
        return

    statement = select(Lead).where(
        Lead.organization_id == org_id,
        or_(*contact_matches),
    )
    if exclude_lead_id:
        statement = statement.where(Lead.id != exclude_lead_id)
    duplicate = (await session.execute(statement.limit(1))).scalar_one_or_none()
    if duplicate is None:
        return

    matched_field = "email" if email and duplicate.email == email else "phone number"
    raise HTTPException(
        status_code=409,
        detail=f"A lead with this {matched_field} already exists.",
    )


async def create_lead(session: AsyncSession, *, org_id: str, actor_id: str, data: LeadCreate) -> Lead:
    values = data.model_dump(mode="json")
    await _reject_duplicate_contact(
        session,
        org_id=org_id,
        email=values["email"],
        phone=values["phone"],
    )
    values["profile_sources"] = {key: "staff_entered" for key in _PROFILE_FIELDS if values[key]}
    lead = Lead(organization_id=org_id, created_by=actor_id, **values)
    session.add(lead)
    await session.flush()
    await change_stage(session, lead=lead, stage="new", actor_id=actor_id, created=True)
    await record_audit(session, action="lead.created", organization_id=org_id, actor_user_id=actor_id,
                       entity_type="lead", entity_id=lead.id, new_values={"name": lead.name, "source": lead.source})
    return lead


async def update_lead(session: AsyncSession, *, org_id: str, actor_id: str,
                      lead_id: str, data: LeadUpdate) -> Lead:
    lead = await get_lead(session, org_id=org_id, lead_id=lead_id)
    changes = data.model_dump(exclude_unset=True, mode="json")
    if "stage" in changes and changes["stage"] not in _STAGES:
        raise HTTPException(status_code=422, detail="Invalid lead stage.")
    if "stage" in changes:
        await change_stage(session, lead=lead, stage=changes.pop("stage"), actor_id=actor_id)
    await _reject_duplicate_contact(
        session,
        org_id=org_id,
        email=changes.get("email"),
        phone=changes.get("phone"),
        exclude_lead_id=lead.id,
    )
    previous_values = {key: getattr(lead, key) for key in changes}
    provenance = dict(lead.profile_sources or {})
    for key in _PROFILE_FIELDS.intersection(changes):
        provenance[key] = "staff_entered" if changes[key] else ""
    lead.profile_sources = provenance
    lead.updated_at = now_utc()
    for key, value in changes.items():
        setattr(lead, key, value)
    session.add(lead)
    await record_audit(session, action="lead.updated", organization_id=org_id, actor_user_id=actor_id,
                       entity_type="lead", entity_id=lead.id,
                       old_values=previous_values, new_values=changes)
    return lead


async def list_trial_slots(session: AsyncSession, *, org_id: str) -> list[dict]:
    rows = (
        await session.execute(
            select(ClassSession).where(
                ClassSession.organization_id == org_id,
                ClassSession.category == "class",
                ClassSession.cancelled == False,  # noqa: E712
                ClassSession.starts_at >= now_utc(),
                ClassSession.booked_count < ClassSession.capacity,
            ).order_by(ClassSession.starts_at).limit(100)
        )
    ).scalars()
    return [
        {
            "id": slot.id,
            "title": slot.title,
            "trainer_member_id": slot.trainer_member_id,
            "starts_at": slot.starts_at,
            "ends_at": slot.ends_at,
            "capacity": slot.capacity,
            "booked_count": slot.booked_count,
            "remaining_capacity": slot.capacity - slot.booked_count,
        }
        for slot in rows
    ]


async def list_lead_bookings(session: AsyncSession, *, org_id: str, lead_id: str) -> list[dict]:
    await get_lead(session, org_id=org_id, lead_id=lead_id)
    rows = (
        await session.execute(
            select(LeadBooking, ClassSession.title)
            .outerjoin(ClassSession, ClassSession.id == LeadBooking.class_session_id)
            .where(
                LeadBooking.organization_id == org_id,
                LeadBooking.lead_id == lead_id,
            )
            .order_by(LeadBooking.starts_at.desc())
        )
    ).all()
    return [_booking_view(booking, class_title) for booking, class_title in rows]


async def create_lead_booking(
    session: AsyncSession,
    *,
    org_id: str,
    actor_id: str,
    lead_id: str,
    booking_type: str,
    class_session_id: str | None,
    trainer_member_id: str | None,
    starts_at,
    ends_at,
    notes: str | None,
) -> dict:
    lead = await _get_locked_lead(session, org_id=org_id, lead_id=lead_id)
    if lead.stage == "joined":
        raise HTTPException(status_code=409, detail="Joined leads cannot book trials or tours.")
    await _reject_active_booking(session, org_id=org_id, lead_id=lead.id)

    class_session = None
    if booking_type == "trial":
        class_session = await _reserve_trial_slot(
            session, org_id=org_id, class_session_id=class_session_id or "",
        )
        starts_at = class_session.starts_at
        ends_at = class_session.ends_at
        trainer_member_id = class_session.trainer_member_id
    else:
        if starts_at is None or starts_at <= now_utc():
            raise HTTPException(status_code=422, detail="Tour time must be in the future.")
        if ends_at is None:
            ends_at = starts_at + timedelta(minutes=30)
        await _validate_trainer(session, org_id=org_id, trainer_member_id=trainer_member_id)

    booking = LeadBooking(
        organization_id=org_id,
        lead_id=lead.id,
        booking_type=booking_type,
        class_session_id=class_session.id if class_session else None,
        trainer_member_id=trainer_member_id,
        starts_at=starts_at,
        ends_at=ends_at,
        status=_ACTIVE_BOOKING_STATUS,
        notes=notes,
        created_by=actor_id,
    )
    session.add(booking)
    await session.flush()
    await change_stage(
        session, lead=lead, stage="trial_booked", actor_id=actor_id,
        origin=f"{booking_type}_booking",
    )
    await record_audit(
        session,
        action="lead.booking_created",
        organization_id=org_id,
        actor_user_id=actor_id,
        entity_type="lead_booking",
        entity_id=booking.id,
        new_values={
            "lead_id": lead.id,
            "booking_type": booking.booking_type,
            "class_session_id": booking.class_session_id,
            "starts_at": booking.starts_at,
            "status": booking.status,
        },
    )
    return _booking_view(booking, class_session.title if class_session else None)


async def update_lead_booking_status(
    session: AsyncSession,
    *,
    org_id: str,
    actor_id: str,
    lead_id: str,
    booking_id: str,
    status: str,
) -> dict:
    if status not in _BOOKING_STATUSES - {_ACTIVE_BOOKING_STATUS}:
        raise HTTPException(status_code=422, detail="Invalid booking status.")
    lead = await _get_locked_lead(session, org_id=org_id, lead_id=lead_id)
    booking = await _get_locked_booking(
        session, org_id=org_id, lead_id=lead.id, booking_id=booking_id,
    )
    class_session = await _booking_class(session, org_id=org_id, booking=booking)
    if booking.status == status:
        return _booking_view(booking, class_session.title if class_session else None)
    if booking.status != _ACTIVE_BOOKING_STATUS:
        raise HTTPException(status_code=409, detail="Completed bookings cannot change status.")

    previous = booking.status
    booking.status = status
    booking.updated_at = now_utc()
    if status == "attended":
        booking.attended_at = now_utc()
        await change_stage(
            session, lead=lead, stage="visited", actor_id=actor_id,
            origin=f"{booking.booking_type}_attendance",
        )
    elif status == "cancelled":
        booking.cancelled_at = now_utc()
        if class_session is not None and class_session.booked_count > 0:
            class_session.booked_count -= 1
            session.add(class_session)
    session.add(booking)
    await record_audit(
        session,
        action="lead.booking_status_changed",
        organization_id=org_id,
        actor_user_id=actor_id,
        entity_type="lead_booking",
        entity_id=booking.id,
        old_values={"status": previous},
        new_values={"status": status},
        metadata={"lead_id": lead.id},
    )
    return _booking_view(booking, class_session.title if class_session else None)


async def _get_locked_lead(session: AsyncSession, *, org_id: str, lead_id: str) -> Lead:
    lead = (
        await session.execute(
            select(Lead).where(Lead.id == lead_id, Lead.organization_id == org_id).with_for_update()
        )
    ).scalar_one_or_none()
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found.")
    return lead


async def _reject_active_booking(session: AsyncSession, *, org_id: str, lead_id: str) -> None:
    existing = (
        await session.execute(
            select(LeadBooking).where(
                LeadBooking.organization_id == org_id,
                LeadBooking.lead_id == lead_id,
                LeadBooking.status == _ACTIVE_BOOKING_STATUS,
            ).limit(1)
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail="This lead already has an active trial or tour.")


async def _reserve_trial_slot(
    session: AsyncSession, *, org_id: str, class_session_id: str,
) -> ClassSession:
    class_session = (
        await session.execute(
            select(ClassSession).where(
                ClassSession.id == class_session_id,
                ClassSession.organization_id == org_id,
            ).with_for_update()
        )
    ).scalar_one_or_none()
    if class_session is None or class_session.category != "class":
        raise HTTPException(status_code=404, detail="Trial class slot not found.")
    if class_session.cancelled or class_session.starts_at <= now_utc():
        raise HTTPException(status_code=409, detail="Trial class slot is no longer available.")
    if class_session.booked_count >= class_session.capacity:
        raise HTTPException(status_code=409, detail="Trial class slot is full.")
    class_session.booked_count += 1
    session.add(class_session)
    return class_session


async def _validate_trainer(
    session: AsyncSession, *, org_id: str, trainer_member_id: str | None,
) -> None:
    if trainer_member_id is None:
        return
    trainer = await session.get(OrganizationMember, trainer_member_id)
    if trainer is None or trainer.organization_id != org_id:
        raise HTTPException(status_code=404, detail="Trainer not found in this organization.")


async def _get_locked_booking(
    session: AsyncSession, *, org_id: str, lead_id: str, booking_id: str,
) -> LeadBooking:
    booking = (
        await session.execute(
            select(LeadBooking).where(
                LeadBooking.id == booking_id,
                LeadBooking.organization_id == org_id,
                LeadBooking.lead_id == lead_id,
            ).with_for_update()
        )
    ).scalar_one_or_none()
    if booking is None:
        raise HTTPException(status_code=404, detail="Lead booking not found.")
    return booking


async def _booking_class(
    session: AsyncSession, *, org_id: str, booking: LeadBooking,
) -> ClassSession | None:
    if booking.class_session_id is None:
        return None
    class_session = await session.get(ClassSession, booking.class_session_id)
    if class_session is None or class_session.organization_id != org_id:
        raise HTTPException(status_code=404, detail="Trial class slot not found.")
    return class_session


def _booking_view(booking: LeadBooking, class_title: str | None) -> dict:
    return {
        "id": booking.id,
        "lead_id": booking.lead_id,
        "booking_type": booking.booking_type,
        "class_session_id": booking.class_session_id,
        "class_title": class_title,
        "trainer_member_id": booking.trainer_member_id,
        "starts_at": booking.starts_at,
        "ends_at": booking.ends_at,
        "status": booking.status,
        "notes": booking.notes,
        "attended_at": booking.attended_at,
        "cancelled_at": booking.cancelled_at,
        "created_at": booking.created_at,
        "updated_at": booking.updated_at,
    }
