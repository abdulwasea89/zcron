"""Inactivity ladder: deterministic escalating outreach for quiet members (#35).

Where the churn-risk score (#34) is a probabilistic judgement, the ladder is a
deterministic, auditable escalation: every member who reaches day N of inactivity
gets the same intervention, in order. Gyms tune the rungs once and trust them.

Default rungs (5 / 10 / 14 / 21 days):

    day 5   nudge        member push/email
    day 10  check-in     member nudge + staff call task
    day 14  return offer member offer + manager task
    day 21  win-back     member message + owner task

Two tables:

* ``InactivityLadderRung`` — the org's configurable ladder.
* ``InactivityLadderProgress`` — one row each time a rung fires for a member.

Reset semantics: a visit ends the inactivity episode. A rung is only "current"
if it fired at or after the member's last visit (``fired_at >= inactive_since``);
once they come back, the same rung fires again on the next stretch, and the old
row remains as history. Frozen members are skipped (a pause is not a relapse).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.constants import (
    LadderStatus,
    MemberStatus,
    NotificationKind,
)
from app.core.security import now_utc
from app.integrations.email import send_email_safe as send_email
from app.models.attendance import Attendance
from app.models.inactivity_ladder import InactivityLadderProgress, InactivityLadderRung
from app.models.membership import OrganizationMember
from app.models.staff import Task
from app.models.user import User
from app.services.audit_service import record_audit

# Members who can still be saved are on the ladder. Frozen = paused, not lost.
_LADDER_STATUSES = {MemberStatus.ACTIVE, MemberStatus.GRACE}


@dataclass(frozen=True)
class DefaultRung:
    day: int
    code: str
    name: str
    member_action: str | None
    staff_action: str | None
    email_subject: str | None
    email_body: str | None


DEFAULT_RUNGS: tuple[DefaultRung, ...] = (
    DefaultRung(
        day=5,
        code="nudge",
        name="Gentle nudge",
        member_action="Send a friendly 'we miss you' nudge",
        staff_action=None,
        email_subject="We miss you at the gym",
        email_body="We haven't seen you in a few days. Even a short session keeps the habit alive — see you soon?",
    ),
    DefaultRung(
        day=10,
        code="check_in",
        name="Check in",
        member_action="Send a check-in nudge",
        staff_action="Call the member and ask what would help",
        email_subject="Everything okay?",
        email_body="It's been over a week. If something's getting in the way, reply — we'll help you find a routine that fits.",
    ),
    DefaultRung(
        day=14,
        code="return_offer",
        name="Return offer",
        member_action="Send a comeback offer",
        staff_action="Manager: offer a free comeback session",
        email_subject="A session on us",
        email_body="Two weeks is a long break. Come back this week and we'll set you up with a complimentary session.",
    ),
    DefaultRung(
        day=21,
        code="win_back",
        name="Win-back",
        member_action="Send a final win-back message",
        staff_action="Owner: final save attempt before win-back",
        email_subject="We'd love to have you back",
        email_body="It's been three weeks. Tell us what went wrong so we can make it right — or pause rather than quit.",
    ),
)


# --------------------------------------------------------------------- config
async def get_config(session: AsyncSession, *, org_id: str) -> list[InactivityLadderRung]:
    """The org's ladder, seeding the defaults on first access."""

    rows = list(
        (
            await session.execute(
                select(InactivityLadderRung)
                .where(InactivityLadderRung.organization_id == org_id)
                .order_by(InactivityLadderRung.day)
            )
        ).scalars().all()
    )
    if not rows:
        rows = await seed_default_ladder(session, org_id=org_id)
    return rows


async def seed_default_ladder(session: AsyncSession, *, org_id: str) -> list[InactivityLadderRung]:
    rows: list[InactivityLadderRung] = []
    for r in DEFAULT_RUNGS:
        row = InactivityLadderRung(
            organization_id=org_id,
            day=r.day,
            code=r.code,
            name=r.name,
            member_action=r.member_action,
            staff_action=r.staff_action,
            email_subject=r.email_subject,
            email_body=r.email_body,
        )
        session.add(row)
        rows.append(row)
    await session.flush()
    return rows


async def update_rung(
    session: AsyncSession,
    *,
    org_id: str,
    day: int,
    member_action: str | None = None,
    staff_action: str | None = None,
    email_subject: str | None = None,
    email_body: str | None = None,
    is_active: bool | None = None,
    actor_user_id: str | None = None,
) -> InactivityLadderRung:
    await get_config(session, org_id=org_id)  # ensure seeded
    rung = (
        await session.execute(
            select(InactivityLadderRung).where(
                InactivityLadderRung.organization_id == org_id,
                InactivityLadderRung.day == day,
            )
        )
    ).scalar_one_or_none()
    if rung is None:
        raise HTTPException(status_code=404, detail="No ladder rung on that day.")
    if member_action is not None:
        rung.member_action = member_action
    if staff_action is not None:
        rung.staff_action = staff_action
    if email_subject is not None:
        rung.email_subject = email_subject
    if email_body is not None:
        rung.email_body = email_body
    if is_active is not None:
        rung.is_active = is_active
    session.add(rung)
    await record_audit(
        session,
        action="inactivity_rung.updated",
        organization_id=org_id,
        actor_user_id=actor_user_id,
        entity_type="inactivity_ladder_rung",
        entity_id=rung.id,
        metadata={"day": day},
    )
    return rung


# ---------------------------------------------------------------------- fire
async def _member_name(session: AsyncSession, member: OrganizationMember) -> str:
    if member.display_name:
        return member.display_name
    user = await session.get(User, member.user_id)
    if user is None:
        return "member"
    return user.full_name or user.email


async def fire_ladder(
    session: AsyncSession,
    *,
    org_id: str,
    member: OrganizationMember,
    inactive_since: datetime,
    days_since: int,
    now: datetime | None = None,
) -> list[InactivityLadderProgress]:
    """Dispatch every due, current rung for one member. Returns new rows."""

    now = now or now_utc()
    if member.member_status not in _LADDER_STATUSES:
        return []

    rungs = await get_config(session, org_id=org_id)
    due = [r for r in rungs if r.is_active and r.day <= days_since]
    if not due:
        return []

    # Rungs already fired during this same inactivity episode (fired_at is not
    # before the episode start).
    fired_now = {
        p.rung_day
        for p in (
            await session.execute(
                select(InactivityLadderProgress).where(
                    InactivityLadderProgress.member_id == member.id,
                    InactivityLadderProgress.fired_at >= inactive_since,
                )
            )
        ).scalars().all()
    }

    name = await _member_name(session, member)
    user = await session.get(User, member.user_id)
    created: list[InactivityLadderProgress] = []

    for rung in due:
        if rung.day in fired_now:
            continue
        channels: list[str] = []

        if rung.email_subject and user is not None:
            await send_email(user.email, rung.email_subject, rung.email_body or rung.email_subject)
            channels.append("email")
        if rung.member_action:
            from app.services.notifications_service import create_notification

            await create_notification(
                session,
                org_id=org_id,
                recipient_user_id=member.user_id,
                category=NotificationKind.MEMBERSHIP,
                title=rung.email_subject or f"We miss you, {name}",
                body=rung.email_body or rung.member_action,
                data={"ladder_day": rung.day, "code": rung.code},
            )
            channels.append("push")
        if rung.staff_action:
            task = Task(
                organization_id=org_id,
                title=f"[Inactivity] {name} — day {rung.day}: {rung.name}",
                description=f"{rung.staff_action}. [mid:{member.id}]",
            )
            session.add(task)
            await session.flush()
            channels.append("task")

        progress = InactivityLadderProgress(
            organization_id=org_id,
            member_id=member.id,
            rung_day=rung.day,
            status=LadderStatus.FIRED,
            fired_at=now,
            channel="+".join(channels) or None,
        )
        session.add(progress)
        created.append(progress)

    if created:
        await session.flush()
        await record_audit(
            session,
            action="inactivity_ladder.fired",
            organization_id=org_id,
            actor_user_id=None,
            entity_type="member",
            entity_id=member.id,
            metadata={"days": [p.rung_day for p in created], "days_since": days_since},
        )
    return created


# ---------------------------------------------------------------------- sweep
async def run_sweep(session: AsyncSession, *, org_id: str) -> dict:
    """Daily: fire due ladder rungs for every live member in the org."""

    await get_config(session, org_id=org_id)  # seed first

    now = now_utc()
    members = (
        await session.execute(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == org_id,
                OrganizationMember.role == "member",
                OrganizationMember.member_status.in_(list(_LADDER_STATUSES)),
            )
        )
    ).scalars().all()
    if not members:
        return {"members": 0, "fired": 0}

    ids = [m.id for m in members]
    visit_agg = {
        mid: None
        for mid in ids
    }
    visit_rows = (
        await session.execute(
            select(Attendance.member_id, func.max(Attendance.checked_in_at))
            .where(
                Attendance.organization_id == org_id,
                Attendance.member_id.in_(ids),
            )
            .group_by(Attendance.member_id)
        )
    ).all()
    for mid, last in visit_rows:
        visit_agg[mid] = last

    fired = 0
    for member in members:
        last = visit_agg.get(member.id)
        inactive_since = last or member.joined_at
        if inactive_since is None:
            continue
        # Never-visited members start their clock at join time.
        days_since = max(0, (now - inactive_since).days)
        fired += len(
            await fire_ladder(
                session,
                org_id=org_id,
                member=member,
                inactive_since=inactive_since,
                days_since=days_since,
                now=now,
            )
        )
    return {"members": len(members), "fired": fired}


# --------------------------------------------------------------------- reads
async def member_ladder(session: AsyncSession, *, org_id: str, member_id: str) -> dict:
    member = await session.get(OrganizationMember, member_id)
    if member is None or member.organization_id != org_id:
        raise HTTPException(status_code=404, detail="Member not found in this organization.")

    rungs = await get_config(session, org_id=org_id)
    progress = list(
        (
            await session.execute(
                select(InactivityLadderProgress)
                .where(
                    InactivityLadderProgress.organization_id == org_id,
                    InactivityLadderProgress.member_id == member_id,
                )
                .order_by(InactivityLadderProgress.fired_at.desc())
            )
        ).scalars().all()
    )
    last = (
        await session.execute(
            select(func.max(Attendance.checked_in_at)).where(
                Attendance.organization_id == org_id,
                Attendance.member_id == member_id,
            )
        )
    ).scalar_one_or_none()
    inactive_since = last or member.joined_at
    days_since = max(0, (now_utc() - inactive_since).days) if inactive_since else None

    # Current episode = rungs fired since the member's last visit.
    current = {
        p.rung_day: p
        for p in progress
        if inactive_since is not None and p.fired_at >= inactive_since
    }
    return {
        "member_id": member.id,
        "name": await _member_name(session, member),
        "status": member.member_status.value if hasattr(member.member_status, "value") else str(member.member_status),
        "days_inactive": days_since,
        "rungs": [
            {
                "day": r.day,
                "code": r.code,
                "name": r.name,
                "member_action": r.member_action,
                "staff_action": r.staff_action,
                "is_active": r.is_active,
                "due": r.is_active and days_since is not None and r.day <= days_since,
                "fired_at": current[r.day].fired_at if r.day in current else None,
                "status": (current[r.day].status.value if r.day in current else None),
                "channel": current[r.day].channel if r.day in current else None,
            }
            for r in rungs
        ],
    }


async def complete_rung(
    session: AsyncSession,
    *,
    org_id: str,
    member_id: str,
    day: int,
    actor_user_id: str | None = None,
    skip: bool = False,
) -> InactivityLadderProgress:
    member = await session.get(OrganizationMember, member_id)
    if member is None or member.organization_id != org_id:
        raise HTTPException(status_code=404, detail="Member not found in this organization.")

    last = (
        await session.execute(
            select(func.max(Attendance.checked_in_at)).where(
                Attendance.organization_id == org_id,
                Attendance.member_id == member_id,
            )
        )
    ).scalar_one_or_none()
    inactive_since = last or member.joined_at

    stmt = (
        select(InactivityLadderProgress)
        .where(
            InactivityLadderProgress.organization_id == org_id,
            InactivityLadderProgress.member_id == member_id,
            InactivityLadderProgress.rung_day == day,
        )
        .order_by(InactivityLadderProgress.fired_at.desc())
    )
    progress = (await session.execute(stmt)).scalars().first()
    if progress is None or (inactive_since is not None and progress.fired_at < inactive_since):
        raise HTTPException(status_code=404, detail="That rung has not fired for this member.")

    progress.status = LadderStatus.SKIPPED if skip else LadderStatus.COMPLETED
    progress.completed_at = now_utc()
    session.add(progress)
    await record_audit(
        session,
        action="inactivity_ladder.rung_closed",
        organization_id=org_id,
        actor_user_id=actor_user_id,
        entity_type="member",
        entity_id=member_id,
        metadata={"day": day, "skipped": skip},
    )
    return progress
