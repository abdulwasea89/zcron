"""Class scheduling & booking service (Sections 8, 9, 15.2).

Owners/managers schedule class sessions and assign trainers. Members book
sessions (idempotent, gated on active membership + capacity). Trainer check-in
flips ``trainer_checked_in``, which is the gate for per-class payroll
(Section 15.2: a class only pays the trainer if they actually checked in).
"""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.constants import AttendanceMethod, AttendanceSource, BookingStatus, MemberStatus, Role
from app.core.security import now_utc
from app.models.class_session import ClassBooking, ClassSession
from app.models.lead import LeadBooking
from app.models.membership import OrganizationMember
from app.models.user import User
from app.realtime import events
from app.schemas.classes import ClassSessionCreate
from app.services import attendance_service, idempotency_service
from app.services.audit_service import record_audit


async def _get_owned_session(session: AsyncSession, org_id: str, class_id: str) -> ClassSession:
    cs = (
        await session.execute(
            select(ClassSession).where(
                ClassSession.id == class_id,
                ClassSession.organization_id == org_id,
            ).with_for_update()
        )
    ).scalar_one_or_none()
    if cs is None:
        raise HTTPException(status_code=404, detail="Class session not found.")
    return cs


async def create_session(
    session: AsyncSession, *, org_id: str, data: ClassSessionCreate, actor_id: str
) -> ClassSession:
    if data.trainer_member_id is not None:
        trainer = await session.get(OrganizationMember, data.trainer_member_id)
        if trainer is None or trainer.organization_id != org_id:
            raise HTTPException(status_code=404, detail="Trainer not found in this org.")
    cs = ClassSession(
        organization_id=org_id,
        title=data.title,
        trainer_member_id=data.trainer_member_id,
        starts_at=data.starts_at,
        ends_at=data.ends_at,
        capacity=data.capacity,
    )
    session.add(cs)
    await session.flush()
    await record_audit(session, action="class.created", organization_id=org_id, actor_user_id=actor_id,
                       entity_type="class_session", entity_id=cs.id)
    await events.class_changed(org_id, class_session_id=cs.id, action="created")
    return cs


async def list_sessions(
    session: AsyncSession, *, org_id: str, include_cancelled: bool = False
) -> list[ClassSession]:
    stmt = select(ClassSession).where(ClassSession.organization_id == org_id)
    if not include_cancelled:
        stmt = stmt.where(ClassSession.cancelled == False)  # noqa: E712
    return list((await session.execute(stmt.order_by(ClassSession.starts_at))).scalars())


async def cancel_session(
    session: AsyncSession, *, org_id: str, class_id: str, actor_id: str
) -> ClassSession:
    cs = await _get_owned_session(session, org_id, class_id)
    cs.cancelled = True
    session.add(cs)
    # Cancel outstanding bookings too.
    bookings = (
        await session.execute(
            select(ClassBooking).where(
                ClassBooking.class_session_id == cs.id,
                ClassBooking.organization_id == org_id,
                ClassBooking.status == BookingStatus.BOOKED,
            )
        )
    ).scalars()
    for b in bookings:
        b.status = BookingStatus.CANCELLED
        session.add(b)
    cs.booked_count = 0
    waitlisted = (
        await session.execute(select(ClassBooking).where(
            ClassBooking.class_session_id == cs.id,
            ClassBooking.organization_id == org_id,
            ClassBooking.status == BookingStatus.WAITLISTED,
        ))
    ).scalars()
    for booking in waitlisted:
        booking.status = BookingStatus.CANCELLED
        session.add(booking)
    trial_bookings = (
        await session.execute(
            select(LeadBooking).where(
                LeadBooking.organization_id == org_id,
                LeadBooking.class_session_id == cs.id,
                LeadBooking.status == "scheduled",
            ).with_for_update()
        )
    ).scalars()
    for booking in trial_bookings:
        booking.status = "cancelled"
        booking.cancelled_at = now_utc()
        session.add(booking)
    await record_audit(session, action="class.cancelled", organization_id=org_id, actor_user_id=actor_id,
                       entity_type="class_session", entity_id=cs.id)
    return cs


async def _member_for(session: AsyncSession, org_id: str, user_id: str) -> OrganizationMember | None:
    return (
        await session.execute(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == org_id,
                OrganizationMember.user_id == user_id,
            )
        )
    ).scalar_one_or_none()


async def book_class(
    session: AsyncSession,
    *,
    org_id: str,
    user_id: str,
    class_session_id: str,
    idempotency_key: str,
) -> ClassBooking:
    """Idempotent member booking (Section 13 applies to class bookings)."""

    member = await _member_for(session, org_id, user_id)
    if member is None:
        raise HTTPException(status_code=404, detail="Membership not found.")
    if member.member_status not in {MemberStatus.ACTIVE, MemberStatus.GRACE}:
        # Grace can keep existing bookings but not make new ones (Section 9.5).
        if member.member_status == MemberStatus.GRACE:
            raise HTTPException(status_code=403, detail="Payment due — cannot book new classes.")
        raise HTTPException(status_code=403, detail="Active membership required to book.")

    cs = await _get_owned_session(session, org_id, class_session_id)
    if cs.cancelled:
        raise HTTPException(status_code=409, detail="Class is cancelled.")

    endpoint = "POST /classes/book"
    claim = await idempotency_service.claim(
        session, key=idempotency_key, endpoint=endpoint,
        body={"class_session_id": class_session_id, "member_id": member.id},
        organization_id=org_id, user_id=user_id,
    )
    if not claim.claimed:
        existing = (
            await session.execute(
                select(ClassBooking).where(ClassBooking.idempotency_key == idempotency_key)
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing
        raise HTTPException(status_code=409, detail="Booking already in progress.")

    # One active booking per member per session.
    dup = (
        await session.execute(
            select(ClassBooking).where(
                ClassBooking.class_session_id == cs.id,
                ClassBooking.member_id == member.id,
                ClassBooking.status == BookingStatus.BOOKED,
            )
        )
    ).scalar_one_or_none()
    if dup is not None:
        await idempotency_service.complete(session, claim.record, code=200, body="{}")
        return dup

    if cs.booked_count >= cs.capacity:
        await idempotency_service.fail(session, claim.record, code=409,
                                       body='{"detail":"Class is full."}')
        raise HTTPException(status_code=409, detail="Class is full.")

    booking = ClassBooking(
        organization_id=org_id,
        class_session_id=cs.id,
        member_id=member.id,
        status=BookingStatus.BOOKED,
        idempotency_key=idempotency_key,
    )
    session.add(booking)
    cs.booked_count += 1
    session.add(cs)
    await session.flush()
    await record_audit(session, action="class.booked", organization_id=org_id, actor_user_id=user_id,
                       entity_type="class_booking", entity_id=booking.id)
    await idempotency_service.complete(session, claim.record, code=200, body="{}")
    return booking


async def cancel_booking(
    session: AsyncSession, *, org_id: str, user_id: str, booking_id: str
) -> ClassBooking:
    booking = await session.get(ClassBooking, booking_id)
    if booking is None or booking.organization_id != org_id:
        raise HTTPException(status_code=404, detail="Booking not found.")
    member = await _member_for(session, org_id, user_id)
    if member is None or booking.member_id != member.id:
        raise HTTPException(status_code=403, detail="Not your booking.")
    if booking.status == BookingStatus.BOOKED:
        cs = await _get_owned_session(session, org_id, booking.class_session_id)
        booking.status = BookingStatus.CANCELLED
        session.add(booking)
        cs.booked_count = max(0, cs.booked_count - 1)
        next_booking = (
            await session.execute(select(ClassBooking).where(
                    ClassBooking.organization_id == org_id,
                    ClassBooking.class_session_id == cs.id,
                    ClassBooking.status == BookingStatus.WAITLISTED,
                ).order_by(ClassBooking.created_at, ClassBooking.id).limit(1).with_for_update())
        ).scalar_one_or_none()
        if next_booking and not cs.cancelled:
            next_booking.status = BookingStatus.BOOKED
            cs.booked_count += 1
            session.add(next_booking)
        session.add(cs)
    return booking


async def add_to_waitlist(
    session: AsyncSession, *, org_id: str, class_id: str, member_id: str, actor_id: str
) -> ClassBooking:
    cs = await _get_owned_session(session, org_id, class_id)
    if cs.cancelled or cs.starts_at <= now_utc():
        raise HTTPException(status_code=409, detail="Only upcoming classes can accept bookings.")
    member = await session.get(OrganizationMember, member_id)
    if member is None or member.organization_id != org_id:
        raise HTTPException(status_code=404, detail="Member not found in this gym.")
    if member.member_status != MemberStatus.ACTIVE:
        raise HTTPException(status_code=409, detail="Only active members can be booked into a class.")
    existing = (await session.execute(select(ClassBooking).where(
        ClassBooking.organization_id == org_id,
        ClassBooking.class_session_id == cs.id,
        ClassBooking.member_id == member.id,
        ClassBooking.status.in_([BookingStatus.BOOKED, BookingStatus.ATTENDED, BookingStatus.WAITLISTED]),
    ))).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Member already has an active booking for this class.")

    status = BookingStatus.BOOKED if cs.booked_count < cs.capacity else BookingStatus.WAITLISTED
    booking = ClassBooking(organization_id=org_id, class_session_id=cs.id, member_id=member.id, status=status)
    session.add(booking)
    if status == BookingStatus.BOOKED:
        cs.booked_count += 1
        session.add(cs)
    await session.flush()
    await record_audit(session, action=f"class.{status.value}", organization_id=org_id,
                       actor_user_id=actor_id, entity_type="class_booking", entity_id=booking.id)
    return booking


async def trainer_check_in(
    session: AsyncSession, *, org_id: str, user_id: str, class_id: str
) -> ClassSession:
    """Trainer marks themselves present, unlocking per-class payroll (Section 15.2)."""

    cs = await _get_owned_session(session, org_id, class_id)
    member = await _member_for(session, org_id, user_id)
    if member is None or member.role not in {Role.TRAINER, Role.OWNER, Role.MANAGER}:
        raise HTTPException(status_code=403, detail="Only the assigned trainer can check in.")
    if cs.trainer_member_id is not None and cs.trainer_member_id != member.id and member.role == Role.TRAINER:
        raise HTTPException(status_code=403, detail="You are not the assigned trainer.")
    cs.trainer_checked_in = True
    session.add(cs)
    await record_audit(session, action="class.trainer_checked_in", organization_id=org_id,
                       actor_user_id=user_id, entity_type="class_session", entity_id=cs.id,
                       metadata={"at": now_utc().isoformat()})
    return cs


async def mark_attended(
    session: AsyncSession, *, org_id: str, class_id: str, booking_id: str, actor_id: str
) -> ClassBooking:
    """Mark a booked member as attended and record the visit (Section 1.8).

    A class booking that turns into a real visit is also a gym visit, so it
    writes one ``Attendance`` row (``source=class``) — the retention model reads
    one behaviour stream, not two.
    """

    cs = await _get_owned_session(session, org_id, class_id)
    booking = await session.get(ClassBooking, booking_id)
    if (
        booking is None
        or booking.organization_id != org_id
        or booking.class_session_id != cs.id
    ):
        raise HTTPException(status_code=404, detail="Booking not found.")
    if booking.status == BookingStatus.CANCELLED:
        raise HTTPException(status_code=409, detail="Booking is cancelled.")

    if booking.status != BookingStatus.ATTENDED:
        booking.status = BookingStatus.ATTENDED
        session.add(booking)

    await attendance_service.record_checkin(
        session,
        org_id=org_id,
        member_id=booking.member_id,
        method=AttendanceMethod.MANUAL,
        source=AttendanceSource.CLASS,
        actor_user_id=actor_id,
        class_session_id=cs.id,
    )
    await record_audit(session, action="class.attended", organization_id=org_id,
                       actor_user_id=actor_id, entity_type="class_booking", entity_id=booking.id)
    return booking


async def mark_no_show(
    session: AsyncSession, *, org_id: str, class_id: str, booking_id: str, actor_id: str
) -> ClassBooking:
    cs = await _get_owned_session(session, org_id, class_id)
    booking = await session.get(ClassBooking, booking_id)
    if booking is None or booking.organization_id != org_id or booking.class_session_id != cs.id:
        raise HTTPException(status_code=404, detail="Booking not found.")
    if booking.status != BookingStatus.BOOKED:
        raise HTTPException(status_code=409, detail="Only booked members can be marked as a no-show.")
    if (cs.ends_at or cs.starts_at) > now_utc():
        raise HTTPException(status_code=409, detail="A class can be marked no-show after it has ended.")
    booking.status = BookingStatus.NO_SHOW
    session.add(booking)
    await record_audit(session, action="class.no_show", organization_id=org_id,
                       actor_user_id=actor_id, entity_type="class_booking", entity_id=booking.id)
    return booking


async def list_bookings(
    session: AsyncSession, *, org_id: str, class_id: str
) -> list[dict]:
    """Return all bookings for a session with member name/email."""
    cs = await _get_owned_session(session, org_id, class_id)
    rows = (
        await session.execute(
            select(ClassBooking, OrganizationMember, User)
            .join(OrganizationMember, OrganizationMember.id == ClassBooking.member_id)
            .join(User, User.id == OrganizationMember.user_id)
            .where(
                ClassBooking.class_session_id == cs.id,
                ClassBooking.organization_id == org_id,
            )
        )
    ).all()
    result = []
    for b, m, u in rows:
        result.append({
            "booking_id": b.id,
            "class_session_id": b.class_session_id,
            "member_id": m.id,
            "member_name": m.display_name or u.full_name,
            "member_email": u.email,
            "status": b.status.value,
        })
    return result


async def list_my_bookings(session: AsyncSession, *, org_id: str, member_id: str) -> list[dict]:
    """A member's own bookings, joined with their sessions (self-service)."""

    rows = (
        await session.execute(
            select(ClassBooking, ClassSession)
            .join(ClassSession, ClassSession.id == ClassBooking.class_session_id)
            .where(
                ClassBooking.organization_id == org_id,
                ClassBooking.member_id == member_id,
            )
        )
    ).all()
    result = []
    for b, cs in rows:
        result.append({
            "booking_id": b.id,
            "status": b.status.value,
            "class_session": {
                "id": cs.id,
                "title": cs.title,
                "trainer_member_id": cs.trainer_member_id,
                "starts_at": cs.starts_at,
                "ends_at": cs.ends_at,
                "capacity": cs.capacity,
                "booked_count": cs.booked_count,
                "trainer_checked_in": cs.trainer_checked_in,
                "cancelled": cs.cancelled,
            },
        })
    return result
