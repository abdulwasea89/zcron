"""Front-desk visitors & lockers service (Section 1.3, #22).

Log walk-ins / day passes / guests, check them out, and manage the locker
register. A day pass with a price writes a Payment (kind=day_pass) so the money
is in the same ledger as member fees and cash.
"""

from __future__ import annotations

from datetime import date, datetime, time
import re

from fastapi import HTTPException
from sqlalchemy import func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.constants import (
    LeadSource,
    LockerStatus,
    PaymentKind,
    PaymentMethod,
    PaymentStatus,
    VisitorKind,
)
from app.core.security import now_utc
from app.models.membership import OrganizationMember
from app.models.user import User
from app.models.visitor import Locker, Visitor
from app.models.payment import Payment
from app.realtime import events
from app.schemas.visitor import LockerAssignIn, LockerIn, VisitorLogIn
from app.schemas.leads import LeadCreate
from app.services.audit_service import record_audit


def _enum(enum_cls, value, default):
    try:
        return enum_cls(value)
    except (ValueError, KeyError):
        return default


def _value(v) -> str:
    return v.value if hasattr(v, "value") else str(v)


async def _host_name(session: AsyncSession, member_id: str | None) -> str | None:
    if not member_id:
        return None
    member = await session.get(OrganizationMember, member_id)
    if member is None:
        return None
    user = await session.get(User, member.user_id)
    return member.display_name or (user.full_name if user else None) or (user.email if user else None)


def _visitor_out(v: Visitor, host_name: str | None) -> dict:
    return {
        "id": v.id,
        "name": v.name,
        "phone": v.phone,
        "email": v.email,
        "kind": _value(v.kind),
        "host_member_id": v.host_member_id,
        "host_name": host_name,
        "amount": v.amount,
        "method": _value(v.method) if v.method else None,
        "paid": v.paid,
        "locker_number": v.locker_number,
        "note": v.note,
        "checked_in_at": v.checked_in_at,
        "checked_out_at": v.checked_out_at,
    }


async def log_visitor(
    session: AsyncSession,
    *,
    org_id: str,
    data: VisitorLogIn,
    actor_user_id: str,
    idempotency_key: str | None = None,
) -> dict:
    """Log a walk-in / day pass / guest. Day passes with a price take payment."""

    if not data.name.strip():
        raise HTTPException(status_code=422, detail="Visitor name is required.")

    # Idempotent replay.
    if idempotency_key:
        existing = (
            await session.execute(
                select(Visitor).where(
                    Visitor.organization_id == org_id,
                    Visitor.idempotency_key == idempotency_key,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return _visitor_out(existing, await _host_name(session, existing.host_member_id))

    kind = _enum(VisitorKind, data.kind, VisitorKind.WALK_IN)
    if data.host_member_id is not None:
        host = await session.get(OrganizationMember, data.host_member_id)
        if host is None or host.organization_id != org_id:
            raise HTTPException(status_code=404, detail="Host member not found.")

    amount = float(data.amount or 0.0)
    if amount < 0:
        raise HTTPException(status_code=422, detail="Amount cannot be negative.")

    method = _enum(PaymentMethod, data.method, PaymentMethod.CASH) if data.method else PaymentMethod.CASH

    visitor = Visitor(
        organization_id=org_id,
        name=data.name.strip(),
        phone=data.phone,
        email=data.email,
        kind=kind,
        host_member_id=data.host_member_id,
        amount=amount,
        method=method if amount > 0 else None,
        note=data.note,
        locker_number=data.locker_number,
        logged_by=actor_user_id,
        idempotency_key=idempotency_key,
    )
    session.add(visitor)
    await session.flush()

    email = (data.email or "").strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        email = ""
    phone = (data.phone or "").strip()
    if len(re.sub(r"\D", "", phone)) < 7:
        phone = ""
    if email or phone:
        contact_match = []
        if email:
            contact_match.append(func.lower(User.email) == email)
        if phone:
            contact_match.append(OrganizationMember.phone == phone)
        known_member = (await session.execute(
            select(OrganizationMember.id)
            .join(User, User.id == OrganizationMember.user_id)
            .where(OrganizationMember.organization_id == org_id, or_(*contact_match))
            .limit(1)
        )).scalar_one_or_none()
        if not known_member:
            from app.services import leads_service

            try:
                await leads_service.create_lead(
                    session, org_id=org_id, actor_id=actor_user_id,
                    data=LeadCreate(
                        name=data.name.strip(), email=email or None, phone=phone or None,
                        source=LeadSource.WALK_IN,
                    ),
                )
            except HTTPException as exc:
                if exc.status_code != 409:
                    raise

    # Day-pass money lands in the payment ledger (member_id is null — no member).
    if amount > 0 and kind == VisitorKind.DAY_PASS:
        payment = Payment(
            organization_id=org_id,
            member_id=None,
            kind=PaymentKind.DAY_PASS,
            method=method,
            status=PaymentStatus.SUCCEEDED,
            amount=amount,
            logged_by=actor_user_id,
            note=f"Day pass — {visitor.name}",
            paid_at=now_utc(),
        )
        session.add(payment)
        await session.flush()
        visitor.payment_id = payment.id
        visitor.paid = True
        session.add(visitor)

    await record_audit(
        session, action="visitor.logged", organization_id=org_id, actor_user_id=actor_user_id,
        entity_type="visitor", entity_id=visitor.id,
        metadata={"kind": kind.value, "amount": amount},
    )
    await events.visitor_changed(org_id, visitor_id=visitor.id, action="logged")
    return _visitor_out(visitor, await _host_name(session, visitor.host_member_id))


async def list_visitors(
    session: AsyncSession,
    *,
    org_id: str,
    day: date | None = None,
    in_only: bool = False,
    limit: int = 200,
) -> list[dict]:
    d = day or now_utc().date()
    start = datetime.combine(d, time.min)
    end = datetime.combine(d, time.max)
    stmt = select(Visitor).where(
        Visitor.organization_id == org_id,
        Visitor.checked_in_at >= start,
        Visitor.checked_in_at <= end,
    )
    if in_only:
        stmt = stmt.where(Visitor.checked_out_at.is_(None))
    rows = (
        await session.execute(stmt.order_by(Visitor.checked_in_at.desc()).limit(limit))
    ).scalars().all()
    out = []
    for v in rows:
        out.append(_visitor_out(v, await _host_name(session, v.host_member_id)))
    return out


async def check_out(
    session: AsyncSession, *, org_id: str, visitor_id: str, actor_id: str
) -> dict:
    visitor = await session.get(Visitor, visitor_id)
    if visitor is None or visitor.organization_id != org_id:
        raise HTTPException(status_code=404, detail="Visitor not found.")
    if visitor.checked_out_at is None:
        visitor.checked_out_at = now_utc()
        session.add(visitor)
        await record_audit(
            session, action="visitor.checked_out", organization_id=org_id, actor_user_id=actor_id,
            entity_type="visitor", entity_id=visitor.id,
        )
        await events.visitor_changed(org_id, visitor_id=visitor.id, action="checked_out")
    return _visitor_out(visitor, await _host_name(session, visitor.host_member_id))


# ------------------------------------------------------------------- lockers
def _locker_out(locker: Locker) -> dict:
    return {
        "id": locker.id,
        "number": locker.number,
        "status": _value(locker.status),
        "holder_label": locker.holder_label,
        "assigned_at": locker.assigned_at,
        "note": locker.note,
    }


async def list_lockers(session: AsyncSession, *, org_id: str) -> list[dict]:
    rows = (
        await session.execute(
            select(Locker).where(Locker.organization_id == org_id).order_by(func.length(Locker.number), Locker.number)
        )
    ).scalars().all()
    return [_locker_out(locker) for locker in rows]


async def create_locker(
    session: AsyncSession, *, org_id: str, data: LockerIn, actor_id: str
) -> dict:
    number = data.number.strip()
    if not number:
        raise HTTPException(status_code=422, detail="Locker number is required.")
    dup = (
        await session.execute(
            select(Locker).where(Locker.organization_id == org_id, Locker.number == number)
        )
    ).scalar_one_or_none()
    if dup is not None:
        raise HTTPException(status_code=409, detail="A locker with that number already exists.")
    locker = Locker(organization_id=org_id, number=number, note=data.note)
    session.add(locker)
    await session.flush()
    await record_audit(
        session, action="locker.created", organization_id=org_id, actor_user_id=actor_id,
        entity_type="locker", entity_id=locker.id, metadata={"number": number},
    )
    return _locker_out(locker)


async def _get_locker(session: AsyncSession, org_id: str, locker_id: str) -> Locker:
    locker = await session.get(Locker, locker_id)
    if locker is None or locker.organization_id != org_id:
        raise HTTPException(status_code=404, detail="Locker not found.")
    return locker


async def assign_locker(
    session: AsyncSession, *, org_id: str, locker_id: str, data: LockerAssignIn, actor_id: str
) -> dict:
    locker = await _get_locker(session, org_id, locker_id)
    if locker.status == LockerStatus.OCCUPIED:
        raise HTTPException(status_code=409, detail="Locker is already occupied.")
    locker.status = LockerStatus.OCCUPIED
    locker.holder_label = data.holder_label.strip()
    locker.assigned_at = now_utc()
    if data.note is not None:
        locker.note = data.note
    session.add(locker)
    await record_audit(
        session, action="locker.assigned", organization_id=org_id, actor_user_id=actor_id,
        entity_type="locker", entity_id=locker.id, metadata={"holder": locker.holder_label},
    )
    return _locker_out(locker)


async def release_locker(
    session: AsyncSession, *, org_id: str, locker_id: str, actor_id: str
) -> dict:
    locker = await _get_locker(session, org_id, locker_id)
    locker.status = LockerStatus.FREE
    locker.holder_label = None
    locker.assigned_at = None
    session.add(locker)
    await record_audit(
        session, action="locker.released", organization_id=org_id, actor_user_id=actor_id,
        entity_type="locker", entity_id=locker.id,
    )
    return _locker_out(locker)


async def summary(session: AsyncSession, *, org_id: str) -> dict:
    start = datetime.combine(now_utc().date(), time.min)
    end = datetime.combine(now_utc().date(), time.max)
    today = int(
        (
            await session.execute(
                select(func.count()).select_from(Visitor).where(
                    Visitor.organization_id == org_id,
                    Visitor.checked_in_at >= start,
                    Visitor.checked_in_at <= end,
                )
            )
        ).scalar_one()
        or 0
    )
    inside = int(
        (
            await session.execute(
                select(func.count()).select_from(Visitor).where(
                    Visitor.organization_id == org_id,
                    Visitor.checked_in_at >= start,
                    Visitor.checked_in_at <= end,
                    Visitor.checked_out_at.is_(None),
                )
            )
        ).scalar_one()
        or 0
    )
    day_pass_revenue = float(
        (
            await session.execute(
                select(func.coalesce(func.sum(Visitor.amount), 0.0)).where(
                    Visitor.organization_id == org_id,
                    Visitor.checked_in_at >= start,
                    Visitor.checked_in_at <= end,
                    Visitor.kind == VisitorKind.DAY_PASS,
                )
            )
        ).scalar_one()
        or 0.0
    )
    occupied = int(
        (
            await session.execute(
                select(func.count()).select_from(Locker).where(
                    Locker.organization_id == org_id,
                    Locker.status == LockerStatus.OCCUPIED,
                )
            )
        ).scalar_one()
        or 0
    )
    total_lockers = int(
        (
            await session.execute(
                select(func.count()).select_from(Locker).where(Locker.organization_id == org_id)
            )
        ).scalar_one()
        or 0
    )
    return {
        "visitors_today": today,
        "inside_now": inside,
        "day_pass_revenue": round(day_pass_revenue, 2),
        "lockers_occupied": occupied,
        "lockers_total": total_lockers,
    }
