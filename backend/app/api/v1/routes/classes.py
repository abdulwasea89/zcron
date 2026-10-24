"""Class session & booking API routes (Sections 8, 9, 15).

Scheduling is staff-managed (admin capability); booking is member-only and
idempotent; trainer check-in gates per-class payroll.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header

from app.api.deps import get_session, get_tenant, require_capability
from app.core.permissions import Capability
from app.core.tenancy import IDEMPOTENCY_HEADER, TenantContext
from app.schemas.classes import (
    BookingCreate,
    BookingOut,
    BookingWithMember,
    ClassSessionCreate,
    ClassSessionOut,
    MyBookingOut,
    WaitlistCreate,
)
from app.schemas.common import Message
from app.services import classes_service as classes
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


def _to_out(cs) -> ClassSessionOut:
    return ClassSessionOut(
        id=cs.id, title=cs.title, trainer_member_id=cs.trainer_member_id,
        starts_at=cs.starts_at, ends_at=cs.ends_at, capacity=cs.capacity,
        booked_count=cs.booked_count, trainer_checked_in=cs.trainer_checked_in,
        cancelled=cs.cancelled,
    )


@router.get("", response_model=list[ClassSessionOut])
async def list_classes(
    ctx: TenantContext = Depends(get_tenant),
    session: AsyncSession = Depends(get_session),
):
    return [_to_out(c) for c in await classes.list_sessions(session, org_id=ctx.org_id)]


@router.get("/my-bookings", response_model=list[MyBookingOut])
async def my_bookings(
    ctx: TenantContext = Depends(get_tenant),
    session: AsyncSession = Depends(get_session),
):
    """A member's own bookings with their sessions (self-service)."""

    member = await classes._member_for(session, ctx.org_id, ctx.user_id)
    if member is None:
        return []
    rows = await classes.list_my_bookings(session, org_id=ctx.org_id, member_id=member.id)
    return [
        MyBookingOut(booking_id=r["booking_id"], status=r["status"], class_session=ClassSessionOut(**r["class_session"]))
        for r in rows
    ]


@router.post("", response_model=ClassSessionOut, status_code=201)
async def create_class(
    data: ClassSessionCreate,
    ctx: TenantContext = Depends(require_capability(Capability.ASSIGN_TASKS)),
    session: AsyncSession = Depends(get_session),
):
    cs = await classes.create_session(session, org_id=ctx.org_id, data=data, actor_id=ctx.user_id)
    return _to_out(cs)


@router.post("/{class_id}/cancel", response_model=ClassSessionOut)
async def cancel_class(
    class_id: str,
    ctx: TenantContext = Depends(require_capability(Capability.ASSIGN_TASKS)),
    session: AsyncSession = Depends(get_session),
):
    cs = await classes.cancel_session(session, org_id=ctx.org_id, class_id=class_id, actor_id=ctx.user_id)
    return _to_out(cs)


@router.post("/{class_id}/check-in", response_model=ClassSessionOut)
async def trainer_check_in(
    class_id: str,
    ctx: TenantContext = Depends(require_capability(Capability.CHECK_IN_SHIFT)),
    session: AsyncSession = Depends(get_session),
):
    cs = await classes.trainer_check_in(session, org_id=ctx.org_id, user_id=ctx.user_id, class_id=class_id)
    return _to_out(cs)


@router.get("/{class_id}/bookings", response_model=list[BookingWithMember])
async def list_bookings(
    class_id: str,
    ctx: TenantContext = Depends(get_tenant),
    session: AsyncSession = Depends(get_session),
):
    return await classes.list_bookings(session, org_id=ctx.org_id, class_id=class_id)


@router.post("/{class_id}/bookings/{booking_id}/attend", response_model=BookingOut)
async def mark_attended(
    class_id: str,
    booking_id: str,
    ctx: TenantContext = Depends(require_capability(Capability.TAKE_ATTENDANCE)),
    session: AsyncSession = Depends(get_session),
):
    """Mark a booked member present; records the visit as gym attendance."""

    booking = await classes.mark_attended(
        session, org_id=ctx.org_id, class_id=class_id, booking_id=booking_id, actor_id=ctx.user_id
    )
    return BookingOut(id=booking.id, class_session_id=booking.class_session_id,
                      member_id=booking.member_id, status=booking.status.value)


@router.post("/{class_id}/bookings/{booking_id}/no-show", response_model=BookingOut)
async def mark_no_show(
    class_id: str,
    booking_id: str,
    ctx: TenantContext = Depends(require_capability(Capability.TAKE_ATTENDANCE)),
    session: AsyncSession = Depends(get_session),
):
    booking = await classes.mark_no_show(
        session, org_id=ctx.org_id, class_id=class_id, booking_id=booking_id, actor_id=ctx.user_id
    )
    return BookingOut(id=booking.id, class_session_id=booking.class_session_id,
                      member_id=booking.member_id, status=booking.status.value)


@router.post("/{class_id}/waitlist", response_model=BookingOut, status_code=201)
async def add_to_waitlist(
    class_id: str,
    data: WaitlistCreate,
    ctx: TenantContext = Depends(require_capability(Capability.CREATE_EDIT_PLANS)),
    session: AsyncSession = Depends(get_session),
):
    booking = await classes.add_to_waitlist(
        session, org_id=ctx.org_id, class_id=class_id, member_id=data.member_id, actor_id=ctx.user_id
    )
    return BookingOut(id=booking.id, class_session_id=booking.class_session_id,
                      member_id=booking.member_id, status=booking.status.value)


@router.post("/book", response_model=BookingOut)
async def book_class(
    data: BookingCreate,
    idempotency_key: str = Header(default="", alias=IDEMPOTENCY_HEADER),
    ctx: TenantContext = Depends(require_capability(Capability.BOOK_CLASSES)),
    session: AsyncSession = Depends(get_session),
):
    booking = await classes.book_class(
        session, org_id=ctx.org_id, user_id=ctx.user_id,
        class_session_id=data.class_session_id, idempotency_key=idempotency_key,
    )
    return BookingOut(id=booking.id, class_session_id=booking.class_session_id,
                      member_id=booking.member_id, status=booking.status.value)


@router.delete("/bookings/{booking_id}", response_model=Message)
async def cancel_booking(
    booking_id: str,
    ctx: TenantContext = Depends(require_capability(Capability.BOOK_CLASSES)),
    session: AsyncSession = Depends(get_session),
):
    await classes.cancel_booking(session, org_id=ctx.org_id, user_id=ctx.user_id, booking_id=booking_id)
    return Message(message="Booking cancelled.")
