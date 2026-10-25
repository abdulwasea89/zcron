"""Tenant-scoped lead profile operations."""

from __future__ import annotations

import json
import re
from statistics import median
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.class_session import ClassSession
from app.models.lead import Lead, LeadBooking, LeadFollowUp
from app.models.membership import OrganizationMember
from app.models.audit_log import AuditLog
from app.models.user import User
from app.models.staff import Task
from app.core.constants import Role
from app.core.security import now_utc
from app.schemas.leads import LeadCreate, LeadUpdate
from app.services.audit_service import record_audit
from app.integrations.email import send_email_safe

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
    if stage in {"joined", "lost"}:
        followups = (
            await session.execute(
                select(LeadFollowUp).where(
                    LeadFollowUp.organization_id == lead.organization_id,
                    LeadFollowUp.lead_id == lead.id,
                    LeadFollowUp.status.in_(["scheduled", "due"]),
                ).with_for_update()
            )
        ).scalars()
        for followup in followups:
            followup.status = "skipped"
            session.add(followup)


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


def speed_to_lead_metrics(leads: list[Lead], staff_names: dict[str, str] | None = None) -> dict:
    """Summarize first recorded contact times for a bounded recent lead set."""
    by_source: dict[str, list[float]] = {}
    by_staff: dict[str, list[float]] = {}
    staff_conversions: dict[str, int] = {}
    source_conversions: dict[str, int] = {}
    response_minutes: list[float] = []
    delivery_confirmed = sum(getattr(lead, "first_contact_delivery_status", "unknown") == "delivered" for lead in leads)
    delivery_failed = sum(getattr(lead, "first_contact_delivery_status", "unknown") == "failed" for lead in leads)
    delivery_unconfirmed = sum(
        lead.first_contact_logged and getattr(lead, "first_contact_delivery_status", "unknown") in {"unknown", "provider_accepted"}
        for lead in leads
    )
    for lead in leads:
        if lead.stage == "joined":
            source_conversions[lead.source] = source_conversions.get(lead.source, 0) + 1
        if not lead.first_contact_logged or lead.first_contacted_at is None:
            continue
        minutes = (lead.first_contacted_at - lead.created_at).total_seconds() / 60
        if minutes < 0:
            continue
        response_minutes.append(minutes)
        by_source.setdefault(lead.source, []).append(minutes)
        if lead.first_contacted_by_user_id:
            by_staff.setdefault(lead.first_contacted_by_user_id, []).append(minutes)
            if lead.stage == "joined":
                staff_conversions[lead.first_contacted_by_user_id] = staff_conversions.get(lead.first_contacted_by_user_id, 0) + 1

    def group_metrics(times: list[float], count: int) -> dict:
        return {
            "leads": count,
            "contacted": len(times),
            "response_rate": round(len(times) / count * 100, 1) if count else 0,
            "median_minutes": round(median(times), 1) if times else None,
        }

    source_counts: dict[str, int] = {}
    for lead in leads:
        source_counts[lead.source] = source_counts.get(lead.source, 0) + 1
    return {
        **group_metrics(response_minutes, len(leads)),
        "delivery_confirmed": delivery_confirmed,
        "delivery_failed": delivery_failed,
        "delivery_unconfirmed": delivery_unconfirmed,
        "uncontacted": sum(
            1 for lead in leads
            if not lead.first_contact_logged and lead.stage not in {"joined", "lost"}
        ),
        "by_source": [
            {
                "source": source,
                **group_metrics(by_source.get(source, []), count),
                "conversions": source_conversions.get(source, 0),
                "conversion_rate": round(source_conversions.get(source, 0) / count * 100, 1),
            }
            for source, count in sorted(source_counts.items())
        ],
        "by_staff": [
            {
                "staff_name": (staff_names or {}).get(staff_id, "Staff member"),
                "contacted": len(times),
                "median_minutes": round(median(times), 1),
                "conversions": staff_conversions.get(staff_id, 0),
                "conversion_rate": round(staff_conversions.get(staff_id, 0) / len(times) * 100, 1),
            }
            for staff_id, times in sorted(by_staff.items(), key=lambda item: (staff_names or {}).get(item[0], "Staff member").casefold())
        ],
    }


async def lead_speed_report(session: AsyncSession, *, org_id: str, days: int) -> dict:
    since = now_utc() - timedelta(days=days)
    rows = (await session.execute(
        select(Lead, User.full_name)
        .outerjoin(User, User.id == Lead.first_contacted_by_user_id)
        .where(Lead.organization_id == org_id, Lead.created_at >= since)
        .order_by(Lead.created_at.desc()).limit(5000)
    )).all()
    leads = [lead for lead, _name in rows]
    staff_names = {
        lead.first_contacted_by_user_id: (name or "Staff member")
        for lead, name in rows if lead.first_contacted_by_user_id
    }
    return {"days": days, **speed_to_lead_metrics(leads, staff_names)}


async def get_lead(session: AsyncSession, *, org_id: str, lead_id: str) -> Lead:
    lead = await session.get(Lead, lead_id)
    if lead is None or lead.organization_id != org_id:
        raise HTTPException(status_code=404, detail="Lead not found.")
    return lead


async def log_first_contact(
    session: AsyncSession, *, org_id: str, lead_id: str, actor_id: str, method: str,
    delivery_status: str = "manual_logged", external_id: str | None = None,
) -> Lead:
    lead = await session.get(Lead, lead_id, with_for_update=True)
    if lead is None or lead.organization_id != org_id:
        raise HTTPException(status_code=404, detail="Lead not found.")
    if lead.stage in {"joined", "lost"}:
        raise HTTPException(status_code=409, detail="A closed lead cannot receive a first-contact log.")
    if lead.first_contact_logged:
        raise HTTPException(status_code=409, detail="The first outreach attempt is already recorded.")
    lead.first_contacted_at = now_utc()
    lead.first_contacted_by_user_id = actor_id
    lead.first_contact_logged = True
    lead.first_contact_delivery_status = delivery_status
    lead.first_contact_external_id = external_id
    session.add(lead)
    await record_audit(
        session, action="lead.first_contact_logged", organization_id=org_id,
        actor_user_id=actor_id, entity_type="lead", entity_id=lead.id,
        metadata={"method": method},
    )
    return lead


async def _reject_duplicate_contact(
    session: AsyncSession,
    *,
    org_id: str,
    email: str | None,
    phone: str | None,
    source: str | None = None,
    contact_handle: str | None = None,
    exclude_lead_id: str | None = None,
) -> None:
    contact_matches = []
    if email:
        contact_matches.append(Lead.email == email)
    if phone:
        digits = re.sub(r"\D", "", phone)
        phone_variants = {digits, f"+{digits}"}
        # Match NANP numbers whether they were entered with +1 or as a local
        # ten-digit number. Punctuation has already been stripped by schema.
        national = digits[1:] if len(digits) == 11 and digits.startswith("1") else digits
        if len(national) == 10:
            phone_variants.update({national, f"+{national}", f"1{national}", f"+1{national}"})
        contact_matches.append(Lead.phone.in_(phone_variants))
    if source and contact_handle:
        contact_matches.append(
            (Lead.source == source) & (func.lower(Lead.contact_handle) == contact_handle.lower())
        )
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

    matched_field = (
        "email" if email and duplicate.email == email
        else "social handle" if contact_handle and duplicate.contact_handle
        and duplicate.contact_handle.casefold() == contact_handle.casefold()
        else "phone number"
    )
    raise HTTPException(
        status_code=409,
        detail=f"A lead with this {matched_field} already exists.",
    )


async def create_lead(session: AsyncSession, *, org_id: str, actor_id: str | None, data: LeadCreate) -> Lead:
    values = data.model_dump(mode="json")
    await _reject_duplicate_contact(
        session,
        org_id=org_id,
        email=values["email"],
        phone=values["phone"],
        source=values["source"],
        contact_handle=values["contact_handle"],
    )
    consent = values.pop("email_followup_consent", False)
    consent_at = now_utc() if consent and values.get("email") else None
    sms_consent = values.pop("sms_followup_consent", False)
    sms_consent = bool(sms_consent and values.get("phone"))
    sms_consent_at = now_utc() if sms_consent else None
    values["profile_sources"] = {key: "staff_entered" for key in _PROFILE_FIELDS if values[key]}
    lead = Lead(
        organization_id=org_id,
        created_by=actor_id,
        email_followup_consent=bool(consent and values.get("email")),
        email_followup_consent_at=consent_at,
        sms_followup_consent=sms_consent,
        sms_followup_consent_at=sms_consent_at,
        **values,
    )
    session.add(lead)
    await session.flush()
    await change_stage(session, lead=lead, stage="new", actor_id=actor_id, created=True)
    for day in (0, 1, 3, 7):
        followup = LeadFollowUp(
            organization_id=org_id,
            lead_id=lead.id,
            day=day,
            due_at=lead.created_at + timedelta(days=day),
            email_status="pending" if lead.email_followup_consent else "skipped",
        )
        session.add(followup)
        if day == 0 and lead.email_followup_consent and lead.email:
            from app.workers.lead_followups import _EMAILS

            subject, template = _EMAILS[0]
            followup.email_attempted_at = now_utc()
            followup.email_attempts = 1
            sent = await send_email_safe(
                lead.email,
                subject,
                template.format(name=lead.name.split()[0]),
            )
            followup.email_status = "sent" if sent else "failed"
            followup.email_sent_at = now_utc() if sent else None
            session.add(followup)
    await record_audit(session, action="lead.created", organization_id=org_id, actor_user_id=actor_id,
                       entity_type="lead", entity_id=lead.id, new_values={"name": lead.name, "source": lead.source})
    return lead


async def list_lead_followups(
    session: AsyncSession, *, org_id: str, lead_id: str,
) -> list[LeadFollowUp]:
    await get_lead(session, org_id=org_id, lead_id=lead_id)
    return list((await session.execute(
        select(LeadFollowUp).where(
            LeadFollowUp.organization_id == org_id,
            LeadFollowUp.lead_id == lead_id,
        ).order_by(LeadFollowUp.day)
    )).scalars())


async def update_lead_followup(
    session: AsyncSession, *, org_id: str, lead_id: str, followup_id: str,
    actor_id: str, status: str, note: str | None,
) -> LeadFollowUp:
    lead = await get_lead(session, org_id=org_id, lead_id=lead_id)
    followup = (await session.execute(
        select(LeadFollowUp).where(
            LeadFollowUp.id == followup_id,
            LeadFollowUp.organization_id == org_id,
            LeadFollowUp.lead_id == lead.id,
        ).with_for_update()
    )).scalar_one_or_none()
    if followup is None:
        raise HTTPException(status_code=404, detail="Lead follow-up not found.")
    if followup.status not in {"due", "completed", "skipped"}:
        raise HTTPException(status_code=409, detail="This follow-up is not due yet.")
    if followup.status in {"completed", "skipped"}:
        raise HTTPException(status_code=409, detail="This follow-up is already closed.")
    if status not in {"completed", "skipped"}:
        raise HTTPException(status_code=422, detail="Invalid follow-up status.")
    followup.status = status
    followup.completed_at = now_utc()
    followup.completed_by = actor_id
    followup.note = note
    session.add(followup)
    await record_audit(
        session, action="lead.followup_updated", organization_id=org_id,
        actor_user_id=actor_id, entity_type="lead_followup", entity_id=followup.id,
        new_values={"day": followup.day, "status": status, "note": note},
    )
    return followup


async def update_lead(session: AsyncSession, *, org_id: str, actor_id: str,
                      lead_id: str, data: LeadUpdate) -> Lead:
    lead = await get_lead(session, org_id=org_id, lead_id=lead_id)
    changes = data.model_dump(exclude_unset=True, mode="json")
    if "email" in changes and changes["email"] != lead.email:
        changes["email_followup_consent"] = False
    if "phone" in changes and changes["phone"] != lead.phone:
        changes["sms_followup_consent"] = False
    if "stage" in changes and changes["stage"] not in _STAGES:
        raise HTTPException(status_code=422, detail="Invalid lead stage.")
    requested_stage = changes.pop("stage", None)
    if requested_stage is not None:
        if requested_stage == "lost" and not changes.get("lost_reason"):
            raise HTTPException(status_code=422, detail="Choose a reason when moving a lead to Lost.")
        await change_stage(session, lead=lead, stage=requested_stage, actor_id=actor_id)
        if requested_stage != "lost":
            changes["lost_reason"] = None
        if requested_stage == "joined" and not lead.converted_member_id:
            email = changes.get("email", lead.email)
            if email:
                matches = (await session.execute(
                    select(OrganizationMember.id)
                    .join(User, User.id == OrganizationMember.user_id)
                    .where(
                        OrganizationMember.organization_id == org_id,
                        OrganizationMember.role == Role.MEMBER,
                        func.lower(User.email) == email.lower(),
                    )
                    .limit(2)
                )).scalars().all()
                if len(matches) == 1:
                    changes["converted_member_id"] = matches[0]
    elif "lost_reason" in changes and lead.stage != "lost":
        raise HTTPException(status_code=422, detail="Lost reason can only be set while the lead is Lost.")
    if "email_followup_consent" in changes:
        opted_in = bool(changes["email_followup_consent"] and changes.get("email", lead.email))
        changes["email_followup_consent"] = opted_in
        changes["email_followup_consent_at"] = now_utc() if opted_in else None
    if "sms_followup_consent" in changes:
        opted_in = bool(changes["sms_followup_consent"] and changes.get("phone", lead.phone))
        changes["sms_followup_consent"] = opted_in
        changes["sms_followup_consent_at"] = now_utc() if opted_in else None
    await _reject_duplicate_contact(
        session,
        org_id=org_id,
        email=changes.get("email"),
        phone=changes.get("phone"),
        source=changes.get("source", lead.source),
        contact_handle=changes.get("contact_handle", lead.contact_handle),
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
    if "email_followup_consent" in changes:
        if changes["email_followup_consent"]:
            followups = (await session.execute(
                select(LeadFollowUp).where(
                    LeadFollowUp.organization_id == org_id,
                    LeadFollowUp.lead_id == lead.id,
                    LeadFollowUp.email_status == "skipped",
                    LeadFollowUp.email_sent_at.is_(None),
                    LeadFollowUp.due_at > now_utc(),
                ).with_for_update()
            )).scalars()
            for followup in followups:
                followup.email_status = "pending"
                session.add(followup)
        else:
            followups = (await session.execute(
                select(LeadFollowUp).where(
                    LeadFollowUp.organization_id == org_id,
                    LeadFollowUp.lead_id == lead.id,
                    LeadFollowUp.email_status == "pending",
                    LeadFollowUp.email_sent_at.is_(None),
                ).with_for_update()
            )).scalars()
            for followup in followups:
                followup.email_status = "skipped"
                session.add(followup)
    await record_audit(session, action="lead.updated", organization_id=org_id, actor_user_id=actor_id,
                       entity_type="lead", entity_id=lead.id,
                       old_values=previous_values, new_values=changes)
    return lead


async def log_missed_call(
    session: AsyncSession, *, org_id: str, lead_id: str, actor_id: str, idempotency_key: str,
) -> dict:
    lead = await get_lead(session, org_id=org_id, lead_id=lead_id)
    actor = (await session.execute(select(OrganizationMember).where(
        OrganizationMember.organization_id == org_id,
        OrganizationMember.user_id == actor_id,
    ))).scalar_one_or_none()
    task = Task(
        organization_id=org_id,
        title=f"Call {lead.name} back",
        description="Follow up after a missed call.",
        assignee_member_id=actor.id if actor else None,
        created_by=actor_id,
        deadline=now_utc() + timedelta(hours=1),
    )
    session.add(task)
    await session.flush()

    status = "skipped_no_phone"
    conversation_id = None
    if lead.phone and lead.sms_followup_consent:
        from app.core.constants import Channel
        from app.services import inbox_service

        conv = await inbox_service.find_or_create(
            session, org_id=org_id, channel=Channel.SMS,
            handle=lead.phone, contact_name=lead.name,
        )
        conversation_id = conv.id
        thread = await inbox_service.reply(
            session, org_id=org_id, user_id=actor_id, conversation_id=conv.id,
            body=f"Hi {lead.name.split()[0]}, sorry we missed your call. Our team will get back to you shortly. Reply STOP to opt out.",
            idempotency_key=f"missed-call:{idempotency_key}",
        )
        status = next(
            (message["delivery_status"] for message in reversed(thread["messages"])
             if message["direction"] == "outbound"),
            "failed",
        )
    elif lead.phone:
        status = "skipped_no_consent"

    await record_audit(
        session, action="lead.missed_call_logged", organization_id=org_id,
        actor_user_id=actor_id, entity_type="lead", entity_id=lead.id,
        metadata={"task_id": task.id, "sms_status": status},
    )
    return {"task_id": task.id, "conversation_id": conversation_id, "sms_status": status}


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
    starts_at: datetime | None,
    ends_at: datetime | None,
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
    class_session = (
        await session.execute(
            select(ClassSession).where(
                ClassSession.id == booking.class_session_id,
                ClassSession.organization_id == org_id,
            ).with_for_update()
        )
    ).scalar_one_or_none()
    if class_session is None:
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
