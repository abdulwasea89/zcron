"""Attendance service: record + read member gym visits (Section 1.3, #18).

The behaviour signal the retention model needs. Every check-in is a tenant-scoped
row; recording one also returns "status on check-in" (membership state, dues,
birthday, days since last visit, at-risk flag) so the front desk can act on the
spot without a second query.

Visits are never blocked on membership status — an expired member's arrival is
still a signal — so the caller records and lets the flags speak (plan decision).
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import func, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.constants import (
    AttendanceMethod,
    AttendanceSource,
    MemberStatus,
    SubscriptionStatus,
)
from app.core.security import now_utc
from app.models.attendance import Attendance
from app.models.membership import OrganizationMember
from app.models.organization import Organization
from app.models.plan import MembershipPlan
from app.models.subscription import Subscription
from app.models.user import User
from app.realtime import events
from app.services.audit_service import record_audit
from app.services.family_service import covered_subscription

# A repeat check-in for the same member within this window is treated as a
# double-tap and replayed rather than stored (only when no idempotency key was
# supplied — an explicit key is authoritative).
_DOUBLE_TAP_SECONDS = 20

# Active members with no visit in this many days are "dormant" / at risk.
_RISK_DAYS = 14

_DUE_STATES = {
    MemberStatus.GRACE,
    MemberStatus.EXPIRED,
    MemberStatus.PENDING_PAYMENT,
}


def _tz(tz_name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(tz_name or "UTC")
    except Exception:
        return ZoneInfo("UTC")


def day_bounds(tz_name: str | None, *, at: datetime | None = None) -> tuple[datetime, datetime]:
    """Naive-UTC [start, end) for the org's local calendar day."""

    tz = _tz(tz_name)
    now = (at or now_utc()).replace(tzinfo=timezone.utc).astimezone(tz)
    start_local = datetime.combine(now.date(), time.min, tzinfo=tz)
    end_local = start_local + timedelta(days=1)
    return (
        start_local.astimezone(timezone.utc).replace(tzinfo=None),
        end_local.astimezone(timezone.utc).replace(tzinfo=None),
    )


async def _get_member(session: AsyncSession, org_id: str, member_id: str) -> OrganizationMember:
    member = await session.get(OrganizationMember, member_id)
    if member is None or member.organization_id != org_id:
        raise HTTPException(status_code=404, detail="Member not found in this organization.")
    return member


def _name(member: OrganizationMember, user: User | None) -> str | None:
    if member.display_name:
        return member.display_name
    if user is None:
        return None
    return user.full_name or user.email


async def _visits_today(
    session: AsyncSession, *, org_id: str, member_id: str, tz_name: str | None
) -> int:
    start, end = day_bounds(tz_name)
    return int(
        (
            await session.execute(
                select(func.count()).select_from(Attendance).where(
                    Attendance.organization_id == org_id,
                    Attendance.member_id == member_id,
                    Attendance.checked_in_at >= start,
                    Attendance.checked_in_at < end,
                )
            )
        ).scalar_one()
        or 0
    )


def _local_today(tz_name: str | None) -> date:
    tz = _tz(tz_name)
    return now_utc().replace(tzinfo=timezone.utc).astimezone(tz).date()


def _birthday_today(user: User | None, tz_name: str | None) -> bool:
    if not user or not user.date_of_birth:
        return False
    today = _local_today(tz_name)
    try:
        return user.date_of_birth.replace(year=today.year) == today
    except ValueError:
        # Feb 29 in a non-leap year: "not today" is the simplest correct answer.
        return False


def _status_value(member: OrganizationMember) -> str:
    return member.member_status.value if hasattr(member.member_status, "value") else str(member.member_status)


def _hint(
    *,
    membership_status: str,
    payment_due: bool,
    amount_due: float | None,
    currency: str | None,
    birthday_today: bool,
    at_risk: bool,
    days_since: int | None,
) -> str | None:
    """One front-desk line: what to say or do for this arrival (Section 1.3)."""

    if membership_status == MemberStatus.EXPIRED.value:
        return "Membership expired — collect payment"
    if payment_due:
        if amount_due is not None:
            return f"Renewal due — {currency or ''}{amount_due:g}"
        return "Dues owed — collect payment"
    if birthday_today:
        return "Birthday today — wish them"
    if at_risk and days_since is not None:
        return f"Back after {days_since} days — welcome them"
    if at_risk and days_since is None:
        return "First visit — welcome them"
    return None


def _build_status(
    *,
    member: OrganizationMember,
    user: User | None,
    tz_name: str | None,
    last_visit: datetime | None,
    renewal: tuple[float | None, str | None] | None,
) -> dict:
    """The status card for one arrival, from already-loaded rows.

    Pure over its inputs so it can be reused per-row in a batch (search, today)
    without extra queries.
    """

    membership_status = _status_value(member)
    payment_due = member.member_status in _DUE_STATES
    amount_due, currency = renewal if renewal else (None, None)
    birthday_today = _birthday_today(user, tz_name)
    days_since = (now_utc() - last_visit).days if last_visit is not None else None

    at_risk = days_since is not None and days_since >= _RISK_DAYS
    if days_since is None and member.joined_at is not None:
        at_risk = (now_utc() - member.joined_at).days >= _RISK_DAYS

    return {
        "membership_status": membership_status,
        "payment_due": payment_due,
        "amount_due": amount_due,
        "currency": currency,
        "birthday_today": birthday_today,
        "days_since_last_visit": days_since,
        "at_risk": at_risk,
        "hint": _hint(
            membership_status=membership_status,
            payment_due=payment_due,
            amount_due=amount_due,
            currency=currency,
            birthday_today=birthday_today,
            at_risk=at_risk,
            days_since=days_since,
        ),
    }


async def _last_visits(
    session: AsyncSession, *, org_id: str, member_ids: list[str], before: datetime | None = None
) -> dict[str, datetime]:
    """Max visit time per member, batched (one query)."""

    if not member_ids:
        return {}
    stmt = (
        select(Attendance.member_id, func.max(Attendance.checked_in_at))
        .where(
            Attendance.organization_id == org_id,
            Attendance.member_id.in_(member_ids),
        )
        .group_by(Attendance.member_id)
    )
    if before is not None:
        stmt = stmt.where(Attendance.checked_in_at < before)
    rows = (await session.execute(stmt)).all()
    return {member_id: last for member_id, last in rows if last is not None}


async def _renewals(
    session: AsyncSession, *, org_id: str, member_ids: list[str]
) -> dict[str, tuple[float | None, str | None]]:
    """Latest grace/expired subscription (amount, currency) per member, batched."""

    if not member_ids:
        return {}
    rows = (
        await session.execute(
            select(Subscription)
            .where(
                Subscription.organization_id == org_id,
                Subscription.member_id.in_(member_ids),
                Subscription.status.in_([SubscriptionStatus.GRACE, SubscriptionStatus.EXPIRED]),
            )
            .order_by(Subscription.created_at.desc())
        )
    ).scalars().all()
    out: dict[str, tuple[float | None, str | None]] = {}
    for s in rows:
        if s.member_id not in out:  # newest first -> first hit wins
            out[s.member_id] = (s.price_snapshot, s.currency)
    return out


async def _status(
    session: AsyncSession,
    *,
    org_id: str,
    member: OrganizationMember,
    user: User | None,
    tz_name: str | None,
    before_at: datetime,
) -> dict:
    """Status-on-check-in flags, measured against visits *before* ``before_at``."""

    last = await _last_visits(session, org_id=org_id, member_ids=[member.id], before=before_at)
    renewal = await _renewals(session, org_id=org_id, member_ids=[member.id])
    return _build_status(
        member=member, user=user, tz_name=tz_name,
        last_visit=last.get(member.id), renewal=renewal.get(member.id),
    )


async def record_checkin(
    session: AsyncSession,
    *,
    org_id: str,
    member_id: str,
    method: AttendanceMethod | str = AttendanceMethod.MANUAL,
    source: AttendanceSource | str = AttendanceSource.FRONT_DESK,
    actor_user_id: str | None = None,
    class_session_id: str | None = None,
    note: str | None = None,
    idempotency_key: str | None = None,
    checked_in_at: datetime | None = None,
) -> dict:
    """Record a member visit and return it with status-on-check-in flags.

    ``checked_in_at`` lets an offline client replay a visit with its real time
    (the sync path); it defaults to now for a live check-in.
    """

    member = await _get_member(session, org_id, member_id)
    user = await session.get(User, member.user_id)
    org = await session.get(Organization, org_id)
    tz_name = org.timezone if org else "UTC"

    method_enum = method if isinstance(method, AttendanceMethod) else AttendanceMethod(str(method))
    source_enum = source if isinstance(source, AttendanceSource) else AttendanceSource(str(source))

    # Replay an explicit idempotency key.
    if idempotency_key:
        existing = (
            await session.execute(
                select(Attendance).where(
                    Attendance.organization_id == org_id,
                    Attendance.idempotency_key == idempotency_key,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            status = await _status(
                session, org_id=org_id, member=member, user=user, tz_name=tz_name,
                before_at=existing.checked_in_at,
            )
            status["visits_today"] = await _visits_today(
                session, org_id=org_id, member_id=member.id, tz_name=tz_name
            )
            return _out(existing, member=member, user=user, status=status)

    # Swallow an accidental double-tap (same member, same method, seconds apart).
    # Only for front-desk logging; class/self events are never collapsed.
    if not idempotency_key and source_enum is AttendanceSource.FRONT_DESK:
        recent = (
            await session.execute(
                select(Attendance).where(
                    Attendance.organization_id == org_id,
                    Attendance.member_id == member.id,
                    Attendance.method == method_enum,
                    Attendance.checked_in_at >= now_utc() - timedelta(seconds=_DOUBLE_TAP_SECONDS),
                )
            )
        ).scalar_one_or_none()
        if recent is not None:
            status = await _status(
                session, org_id=org_id, member=member, user=user, tz_name=tz_name,
                before_at=recent.checked_in_at,
            )
            status["visits_today"] = await _visits_today(
                session, org_id=org_id, member_id=member.id, tz_name=tz_name
            )
            return _out(recent, member=member, user=user, status=status)

    at = checked_in_at or now_utc()
    if at.tzinfo is not None:
        at = at.astimezone(timezone.utc).replace(tzinfo=None)
    sub = await covered_subscription(session, org_id, member)
    access_warning = None
    credit_subscription_id = None
    valid_until = (sub.grace_until if sub.status == SubscriptionStatus.GRACE and sub.grace_until else sub.current_period_end) if sub else None
    if member.banned or member.member_status not in {MemberStatus.ACTIVE, MemberStatus.GRACE}:
        access_warning = "Membership is not active."
    elif sub is None:
        access_warning = "No active plan covers this visit."
    elif valid_until and at > valid_until:
        access_warning = "Plan validity has ended."
    else:
        plan = await session.get(MembershipPlan, sub.plan_id)
        if plan and plan.off_peak_start and plan.off_peak_end:
            local_time = at.replace(tzinfo=timezone.utc).astimezone(_tz(tz_name)).strftime("%H:%M")
            start, end = plan.off_peak_start, plan.off_peak_end
            permitted = start <= local_time < end if start < end else local_time >= start or local_time < end
            if not permitted:
                access_warning = f"This plan is valid from {start} to {end} local time."
        if access_warning is None and sub.classes_remaining is not None:
            consumed = await session.execute(
                update(Subscription).where(
                    Subscription.id == sub.id,
                    Subscription.organization_id == org_id,
                    Subscription.classes_remaining > 0,
                ).values(classes_remaining=Subscription.classes_remaining - 1)
            )
            if consumed.rowcount:
                credit_subscription_id = sub.id
            else:
                access_warning = "No visit credits remaining."
    row = Attendance(
        organization_id=org_id,
        member_id=member.id,
        checked_in_at=at,
        method=method_enum,
        source=source_enum,
        checked_in_by=actor_user_id,
        class_session_id=class_session_id,
        note=note,
        idempotency_key=idempotency_key,
        credit_subscription_id=credit_subscription_id,
    )
    session.add(row)
    await session.flush()

    status = await _status(
        session, org_id=org_id, member=member, user=user, tz_name=tz_name, before_at=at
    )
    status["visits_today"] = await _visits_today(
        session, org_id=org_id, member_id=member.id, tz_name=tz_name
    )
    status["access_warning"] = access_warning
    if access_warning:
        status["hint"] = access_warning

    await record_audit(
        session,
        action="attendance.check_in",
        organization_id=org_id,
        actor_user_id=actor_user_id,
        entity_type="attendance",
        entity_id=row.id,
        metadata={"member_id": member.id, "method": method_enum.value, "source": source_enum.value},
    )
    await events.attendance_checked_in(org_id, member_id=member.id, attendance_id=row.id)
    return _out(row, member=member, user=user, status=status)


def _out(
    row: Attendance,
    *,
    member: OrganizationMember,
    user: User | None,
    status: dict,
) -> dict:
    return {
        "id": row.id,
        "member_id": row.member_id,
        "member_name": _name(member, user),
        "checked_in_at": row.checked_in_at,
        "method": row.method.value if hasattr(row.method, "value") else str(row.method),
        "source": row.source.value if hasattr(row.source, "value") else str(row.source),
        "class_session_id": row.class_session_id,
        "note": row.note,
        "credit_consumed": row.credit_subscription_id is not None,
        **status,
    }


async def list_today(
    session: AsyncSession, *, org_id: str, tz_name: str | None, limit: int = 200
) -> list[dict]:
    """Today's check-ins with member names and their status card, newest first."""

    start, end = day_bounds(tz_name)
    rows = (
        await session.execute(
            select(Attendance, OrganizationMember, User)
            .join(OrganizationMember, OrganizationMember.id == Attendance.member_id)
            .outerjoin(User, User.id == OrganizationMember.user_id)
            .where(
                Attendance.organization_id == org_id,
                Attendance.checked_in_at >= start,
                Attendance.checked_in_at < end,
            )
            .order_by(Attendance.checked_in_at.desc())
            .limit(limit)
        )
    ).all()

    member_ids = list({m.id for _r, m, _u in rows})
    prior = await _last_visits(session, org_id=org_id, member_ids=member_ids, before=start)
    renewals = await _renewals(session, org_id=org_id, member_ids=member_ids)

    out: list[dict] = []
    for r, m, u in rows:
        status = _build_status(
            member=m, user=u, tz_name=tz_name,
            last_visit=prior.get(m.id), renewal=renewals.get(m.id),
        )
        out.append(_out(r, member=m, user=u, status=status))
    return out


async def list_for_member(
    session: AsyncSession, *, org_id: str, member_id: str, limit: int = 50
) -> list[dict]:
    """A member's visit history, newest first."""

    member = await _get_member(session, org_id, member_id)
    user = await session.get(User, member.user_id)
    rows = (
        await session.execute(
            select(Attendance)
            .where(
                Attendance.organization_id == org_id,
                Attendance.member_id == member_id,
            )
            .order_by(Attendance.checked_in_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    return [_out(r, member=member, user=user, status={}) for r in rows]


async def last_visit_at(
    session: AsyncSession, *, org_id: str, member_id: str
) -> datetime | None:
    return (
        await session.execute(
            select(func.max(Attendance.checked_in_at)).where(
                Attendance.organization_id == org_id,
                Attendance.member_id == member_id,
            )
        )
    ).scalar_one_or_none()


async def summary(
    session: AsyncSession, *, org_id: str, tz_name: str | None
) -> dict:
    """Front-desk headline numbers for today (org-local day)."""

    start, end = day_bounds(tz_name)
    today_count = int(
        (
            await session.execute(
                select(func.count()).select_from(Attendance).where(
                    Attendance.organization_id == org_id,
                    Attendance.checked_in_at >= start,
                    Attendance.checked_in_at < end,
                )
            )
        ).scalar_one()
        or 0
    )
    unique_today = int(
        (
            await session.execute(
                select(func.count(func.distinct(Attendance.member_id))).where(
                    Attendance.organization_id == org_id,
                    Attendance.checked_in_at >= start,
                    Attendance.checked_in_at < end,
                )
            )
        ).scalar_one()
        or 0
    )

    week_start = start - timedelta(days=6)
    week_count = int(
        (
            await session.execute(
                select(func.count()).select_from(Attendance).where(
                    Attendance.organization_id == org_id,
                    Attendance.checked_in_at >= week_start,
                    Attendance.checked_in_at < end,
                )
            )
        ).scalar_one()
        or 0
    )

    risk_start = now_utc() - timedelta(days=_RISK_DAYS)
    active_members = int(
        (
            await session.execute(
                select(func.count()).select_from(OrganizationMember).where(
                    OrganizationMember.organization_id == org_id,
                    OrganizationMember.role == "member",
                    OrganizationMember.member_status == MemberStatus.ACTIVE,
                )
            )
        ).scalar_one()
        or 0
    )
    recent_visitors = (
        await session.execute(
            select(func.count(func.distinct(Attendance.member_id))).where(
                Attendance.organization_id == org_id,
                Attendance.checked_in_at >= risk_start,
            )
        )
    ).scalar_one() or 0
    dormant = max(0, active_members - int(recent_visitors))

    return {
        "today_count": today_count,
        "unique_today": unique_today,
        "avg_last_7_days": round(week_count / 7, 1),
        "dormant_members": dormant,
    }


async def summary_for_org(session: AsyncSession, *, org_id: str) -> dict:
    """``summary`` with the org's timezone resolved internally."""

    org = await session.get(Organization, org_id)
    return await summary(session, org_id=org_id, tz_name=org.timezone if org else "UTC")


async def list_roster(
    session: AsyncSession, *, org_id: str, limit: int = 2000
) -> list[dict]:
    """Everyone in the org, for offline check-in search (#23).

    The front desk caches this so it can still find a member when the network is
    down. Gated by ``TAKE_ATTENDANCE`` — no admin directory needed.
    """

    rows = (
        await session.execute(
            select(OrganizationMember, User)
            .join(User, User.id == OrganizationMember.user_id)
            .where(OrganizationMember.organization_id == org_id)
            .order_by(User.full_name, User.email)
            .limit(max(1, min(limit, 5000)))
        )
    ).all()
    return [
        {
            "member_id": m.id,
            "member_name": _name(m, u),
            "member_email": u.email,
            "member_status": _status_value(m),
            "phone": m.phone,
            "has_attendance_card": bool(m.attendance_card_uid),
        }
        for m, u in rows
    ]


async def search_members(
    session: AsyncSession, *, org_id: str, q: str, tz_name: str | None = None, limit: int = 8
) -> list[dict]:
    """Search everyone in the org by name/email/phone for the check-in box.

    Not limited to ``role == member``: owners, managers, trainers and front desk
    often hold their own membership at the venue, so a staff member arriving for
    a workout is checkable too (same rule as the cash-logging search). Gated by
    ``TAKE_ATTENDANCE`` at the route layer, which is why this does not reuse the
    admin member directory.

    Each hit carries its status card (dues / birthday / at-risk + hint) so the
    desk sees it before tapping.
    """

    term = q.strip()
    if not term:
        return []
    pattern = f"%{term.lower()}%"
    rows = (
        await session.execute(
            select(OrganizationMember, User)
            .join(User, User.id == OrganizationMember.user_id)
            .where(
                OrganizationMember.organization_id == org_id,
                func.lower(func.coalesce(OrganizationMember.display_name, User.full_name, "")).like(pattern)
                | func.lower(User.email).like(pattern)
                | func.coalesce(OrganizationMember.phone, "").like(f"%{term}%"),
            )
            .order_by(User.full_name, User.email)
            .limit(max(1, min(limit, 25)))
        )
    ).all()

    member_ids = [m.id for m, _u in rows]
    last = await _last_visits(session, org_id=org_id, member_ids=member_ids)
    renewals = await _renewals(session, org_id=org_id, member_ids=member_ids)

    out: list[dict] = []
    for m, u in rows:
        status = _build_status(
            member=m, user=u, tz_name=tz_name,
            last_visit=last.get(m.id), renewal=renewals.get(m.id),
        )
        out.append({
            "member_id": m.id,
            "member_name": _name(m, u),
            "member_email": u.email,
            "phone": m.phone,
            "has_attendance_card": bool(m.attendance_card_uid),
            "member_status": status["membership_status"],
            "payment_due": status["payment_due"],
            "amount_due": status["amount_due"],
            "currency": status["currency"],
            "birthday_today": status["birthday_today"],
            "at_risk": status["at_risk"],
            "days_since_last_visit": status["days_since_last_visit"],
            "hint": status["hint"],
        })
    return out
