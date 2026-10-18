"""90-day onboarding journey service (#32).

A new member's first 90 days are the highest-leverage window for retention. This
service owns the journey clock: it starts a journey when a member becomes ACTIVE,
advances it one calendar day at a time, fires the day-based milestones (member
nudges + staff actions), tracks attendance adherence, and closes the journey at
day 90.

The milestone catalog is code (``CATALOG``) rather than a table: it is versioned
with the app and needs no per-tenant seed rows. Per-member state lives in
``OnboardingMilestoneProgress``.

Design notes:

* Milestones fire once, tracked by ``(journey_id, code)``.
* A milestone more than ``_FRESH_DAYS`` past its due date is completed silently
  (no email/notification). This makes the daily worker safe to run against
  existing members — backfilled journeys do not spam anyone.
* Non-attendance is the strongest churn predictor (blueprint): a member past
  day 7 with zero visits in the last 7 days raises exactly one staff task.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.constants import (
    MemberStatus,
    MilestoneStatus,
    NotificationKind,
    OnboardingStatus,
    Role,
)
from app.core.security import now_utc
from app.integrations.email import send_email_safe as send_email
from app.models.attendance import Attendance
from app.models.membership import OrganizationMember
from app.models.onboarding import OnboardingJourney, OnboardingMilestoneProgress
from app.models.staff import Task
from app.models.user import User
from app.services.audit_service import record_audit

JOURNEY_DAYS = 90

# A milestone this many days past its due date is closed silently (backfill /
# worker downtime must not spam the member).
_FRESH_DAYS = 7

# Members with no visit for this long pause the check-in nudges.
_QUIET_DAY = 7


@dataclass(frozen=True)
class Milestone:
    day: int
    code: str
    title: str
    member_action: str | None
    staff_action: str | None
    email_subject: str | None
    email_body: str | None


CATALOG: tuple[Milestone, ...] = (
    Milestone(
        day=0,
        code="welcome",
        title="Welcome — let's get you started",
        member_action="Set your goals and preferred training times",
        staff_action=None,
        email_subject="Welcome aboard!",
        email_body="Your membership is active. Tell us your goals so we can tailor your first weeks.",
    ),
    Milestone(
        day=3,
        code="first_checkin",
        title="How's it going?",
        member_action="Complete your first visit",
        staff_action="Call the member if they have not visited yet",
        email_subject="How's your first week going?",
        email_body="We'd love to see you at the gym. Reply if you need a hand getting started.",
    ),
    Milestone(
        day=7,
        code="week_1",
        title="Week 1 complete",
        member_action="Book a class this week",
        staff_action="Check in if fewer than 2 visits this week",
        email_subject="Your first week — keep the momentum",
        email_body="You've made it a week. Try to book your next class now while it's on your mind.",
    ),
    Milestone(
        day=14,
        code="week_2",
        title="Two weeks in",
        member_action="Try a class you haven't done before",
        staff_action="Suggest a personal-training session",
        email_subject="Two weeks strong",
        email_body="Mix it up this week — exploring a new class keeps training interesting.",
    ),
    Milestone(
        day=30,
        code="month_1",
        title="One month — a habit forming",
        member_action="Review your progress with us",
        staff_action="Book a 15-minute check-in",
        email_subject="One month down",
        email_body="A full month in. Let's review your goals and set the next target together.",
    ),
    Milestone(
        day=60,
        code="month_2",
        title="Building momentum",
        member_action="Set your next month's goal",
        staff_action=None,
        email_subject="Two months in",
        email_body="You're building real momentum. What's your goal for the next month?",
    ),
    Milestone(
        day=90,
        code="graduate",
        title="You did it — 90 days",
        member_action="Refer a friend and celebrate",
        staff_action=None,
        email_subject="90 days — you've graduated!",
        email_body="You've built a real habit. Bring a friend along this week and keep it going.",
    ),
)

CATALOG_BY_CODE: dict[str, Milestone] = {m.code: m for m in CATALOG}


# --------------------------------------------------------------------- helpers
async def _get_member(session: AsyncSession, org_id: str, member_id: str) -> OrganizationMember:
    member = await session.get(OrganizationMember, member_id)
    if member is None or member.organization_id != org_id:
        raise HTTPException(status_code=404, detail="Member not found in this organization.")
    return member


async def _get_journey(session: AsyncSession, org_id: str, member_id: str) -> OnboardingJourney | None:
    return (
        await session.execute(
            select(OnboardingJourney).where(
                OnboardingJourney.organization_id == org_id,
                OnboardingJourney.member_id == member_id,
            )
        )
    ).scalar_one_or_none()


async def _visits_since(
    session: AsyncSession, *, org_id: str, member_id: str, since: datetime, classes_only: bool = False
) -> int:
    stmt = select(func.count()).select_from(Attendance).where(
        Attendance.organization_id == org_id,
        Attendance.member_id == member_id,
        Attendance.checked_in_at >= since,
    )
    if classes_only:
        stmt = stmt.where(Attendance.class_session_id != None)  # noqa: E711
    return int((await session.execute(stmt)).scalar_one() or 0)


async def _notify_member(
    session: AsyncSession, member: OrganizationMember, *, title: str, body: str, data: dict | None = None
) -> None:
    from app.services.notifications_service import create_notification

    user = await session.get(User, member.user_id)
    if user is not None:
        await send_email(user.email, title, body)
    await create_notification(
        session,
        org_id=member.organization_id,
        recipient_user_id=member.user_id,
        category=NotificationKind.ONBOARDING,
        title=title,
        body=body,
        data=data,
    )


async def _raise_quiet_task(
    session: AsyncSession, *, journey: OnboardingJourney, member: OrganizationMember, day: int
) -> None:
    """One staff task when a member goes quiet (no visits) past day 7."""

    from app.services.notifications_service import notify_org_owners

    user = await session.get(User, member.user_id)
    name = member.display_name or (user.full_name if user else None) or (user.email if user else member.id)
    task = Task(
        organization_id=member.organization_id,
        title=f"[Onboarding] Reach out to {name} — no visits in a week (day {day})",
        description="New member has not visited in the last 7 days. Call or message today — early churn signal.",
        assignee_member_id=journey.assigned_trainer_id,
    )
    session.add(task)
    await session.flush()

    if journey.assigned_trainer_id:
        trainer = await session.get(OrganizationMember, journey.assigned_trainer_id)
        if trainer is not None:
            from app.services.notifications_service import create_notification

            await create_notification(
                session,
                org_id=member.organization_id,
                recipient_user_id=trainer.user_id,
                category=NotificationKind.TASK,
                title="New task assigned",
                body=task.description,
                data={"task_id": task.id},
            )
    else:
        await notify_org_owners(
            session,
            org_id=member.organization_id,
            category=NotificationKind.TASK,
            title="New member going quiet",
            body=f"{name} hasn't visited in a week. Assign a check-in.",
            data={"member_id": member.id},
        )
    journey.quiet_flag_at = now_utc()
    session.add(journey)


async def _fire_milestone(
    session: AsyncSession,
    *,
    journey: OnboardingJourney,
    milestone: Milestone,
    member: OrganizationMember,
    notify: bool,
) -> OnboardingMilestoneProgress:
    progress = OnboardingMilestoneProgress(
        organization_id=member.organization_id,
        journey_id=journey.id,
        member_id=member.id,
        day=milestone.day,
        code=milestone.code,
        status=MilestoneStatus.PENDING,
    )
    session.add(progress)
    await session.flush()

    if notify:
        if milestone.email_subject:
            await _notify_member(
                session,
                member,
                title=milestone.email_subject,
                body=milestone.email_body or milestone.title,
                data={"milestone": milestone.code, "day": milestone.day},
            )
        if milestone.staff_action:
            task = Task(
                organization_id=member.organization_id,
                title=f"[Onboarding] {milestone.title}",
                description=milestone.staff_action,
                assignee_member_id=journey.assigned_trainer_id,
            )
            session.add(task)
            await session.flush()
    return progress


# ------------------------------------------------------------------ start
async def start_journey(
    session: AsyncSession,
    *,
    org_id: str,
    member_id: str,
    assigned_trainer_id: str | None = None,
    notify: bool = True,
) -> OnboardingJourney:
    """Start (or return) the onboarding journey for a member.

    Idempotent: a repeat call returns the existing journey. The day-0 milestone
    is fired via ``advance_journey`` so a backfilled member (``notify=False``)
    gets the same state without the welcome spam.
    """

    existing = await _get_journey(session, org_id, member_id)
    if existing is not None:
        return existing

    member = await _get_member(session, org_id, member_id)
    journey = OnboardingJourney(
        organization_id=org_id,
        member_id=member.id,
        status=OnboardingStatus.ACTIVE,
        started_at=member.joined_at or now_utc(),
        assigned_trainer_id=assigned_trainer_id or member.referred_by_member_id,
    )
    session.add(journey)
    await session.flush()

    await record_audit(
        session,
        action="onboarding.started",
        organization_id=org_id,
        actor_user_id=member.user_id,
        entity_type="onboarding_journey",
        entity_id=journey.id,
        metadata={"member_id": member.id},
    )
    await advance_journey(session, journey=journey, member=member, notify=notify)
    return journey


# ------------------------------------------------------------------ advance
async def advance_journey(
    session: AsyncSession,
    *,
    journey: OnboardingJourney,
    member: OrganizationMember,
    now: datetime | None = None,
    notify: bool = True,
) -> OnboardingJourney:
    """Advance one journey to today: counters, milestones, quiet task, close."""

    now = now or now_utc()

    # Membership status drives the journey status (freeze pauses, cancel opts out).
    if member.member_status in {MemberStatus.CANCELLED, MemberStatus.BANNED, MemberStatus.EXPIRED}:
        journey.status = OnboardingStatus.OPTED_OUT
        session.add(journey)
        return journey
    if member.member_status == MemberStatus.FROZEN:
        if journey.status == OnboardingStatus.ACTIVE:
            journey.status = OnboardingStatus.PAUSED
            session.add(journey)
        return journey
    if journey.status == OnboardingStatus.PAUSED and member.member_status == MemberStatus.ACTIVE:
        journey.status = OnboardingStatus.ACTIVE
    if journey.status != OnboardingStatus.ACTIVE:
        return journey

    elapsed = max(0, (now - journey.started_at).days)
    new_day = min(JOURNEY_DAYS, elapsed)

    journey.visits_total = await _visits_since(
        session, org_id=member.organization_id, member_id=member.id, since=journey.started_at
    )
    journey.visits_last_7d = await _visits_since(
        session,
        org_id=member.organization_id,
        member_id=member.id,
        since=now - timedelta(days=7),
    )
    journey.classes_attended = await _visits_since(
        session,
        org_id=member.organization_id,
        member_id=member.id,
        since=journey.started_at,
        classes_only=True,
    )

    fired = {
        row.code
        for row in (
            await session.execute(
                select(OnboardingMilestoneProgress).where(
                    OnboardingMilestoneProgress.journey_id == journey.id
                )
            )
        ).scalars().all()
    }
    for milestone in CATALOG:
        if milestone.day > new_day or milestone.code in fired:
            continue
        fresh = (new_day - milestone.day) <= _FRESH_DAYS
        await _fire_milestone(
            session, journey=journey, milestone=milestone, member=member, notify=notify and fresh
        )

    if (
        new_day >= _QUIET_DAY
        and journey.visits_last_7d == 0
        and journey.quiet_flag_at is None
    ):
        await _raise_quiet_task(session, journey=journey, member=member, day=new_day)

    journey.current_day = new_day
    if new_day >= JOURNEY_DAYS:
        journey.status = OnboardingStatus.COMPLETED
        journey.completed_at = now
    session.add(journey)
    return journey


# ---------------------------------------------------------------- progress
async def progress_journeys(session: AsyncSession, *, org_id: str) -> dict:
    """Daily sweep for one org: backfill missing journeys, advance the rest."""

    members = (
        await session.execute(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == org_id,
                OrganizationMember.role == Role.MEMBER,
                OrganizationMember.joined_at != None,  # noqa: E711
            )
        )
    ).scalars().all()

    existing = {
        j.member_id
        for j in (
            await session.execute(
                select(OnboardingJourney).where(OnboardingJourney.organization_id == org_id)
            )
        ).scalars().all()
    }

    started = 0
    for member in members:
        if member.member_status == MemberStatus.ACTIVE and member.id not in existing:
            await start_journey(session, org_id=org_id, member_id=member.id, notify=False)
            started += 1

    journeys = (
        await session.execute(
            select(OnboardingJourney).where(OnboardingJourney.organization_id == org_id)
        )
    ).scalars().all()
    advanced = 0
    for journey in journeys:
        member = await session.get(OrganizationMember, journey.member_id)
        if member is None:
            continue
        await advance_journey(session, journey=journey, member=member)
        advanced += 1
    return {"started": started, "advanced": advanced}


# ---------------------------------------------------------------- mutations
async def complete_milestone(
    session: AsyncSession,
    *,
    org_id: str,
    member_id: str,
    code: str,
    actor_user_id: str | None = None,
    completed_by_member_id: str | None = None,
    notes: str | None = None,
) -> OnboardingMilestoneProgress:
    journey = await _get_journey(session, org_id, member_id)
    if journey is None:
        raise HTTPException(status_code=404, detail="This member has no onboarding journey.")
    if code not in CATALOG_BY_CODE:
        raise HTTPException(status_code=404, detail="Unknown milestone.")
    progress = (
        await session.execute(
            select(OnboardingMilestoneProgress).where(
                OnboardingMilestoneProgress.journey_id == journey.id,
                OnboardingMilestoneProgress.code == code,
            )
        )
    ).scalar_one_or_none()
    if progress is None:
        raise HTTPException(status_code=404, detail="That milestone has not been reached yet.")

    progress.status = MilestoneStatus.COMPLETED
    progress.completed_at = now_utc()
    progress.completed_by = completed_by_member_id
    if notes:
        progress.notes = notes
    session.add(progress)
    await record_audit(
        session,
        action="onboarding.milestone_completed",
        organization_id=org_id,
        actor_user_id=actor_user_id,
        entity_type="onboarding_progress",
        entity_id=progress.id,
        metadata={"member_id": member_id, "code": code},
    )
    return progress


async def set_journey_status(
    session: AsyncSession, *, org_id: str, member_id: str, pause: bool
) -> OnboardingJourney:
    journey = await _get_journey(session, org_id, member_id)
    if journey is None:
        raise HTTPException(status_code=404, detail="This member has no onboarding journey.")
    if pause:
        journey.status = OnboardingStatus.PAUSED
    elif journey.status == OnboardingStatus.PAUSED:
        journey.status = OnboardingStatus.ACTIVE
    session.add(journey)
    return journey


# ------------------------------------------------------------------- reads
def _journey_dict(journey: OnboardingJourney, *, member_name: str | None = None) -> dict:
    return {
        "id": journey.id,
        "member_id": journey.member_id,
        "member_name": member_name,
        "status": journey.status.value if hasattr(journey.status, "value") else str(journey.status),
        "started_at": journey.started_at,
        "completed_at": journey.completed_at,
        "current_day": journey.current_day,
        "total_days": JOURNEY_DAYS,
        "assigned_trainer_id": journey.assigned_trainer_id,
        "visits_total": journey.visits_total,
        "visits_last_7d": journey.visits_last_7d,
        "classes_attended": journey.classes_attended,
        "at_risk": journey.current_day >= _QUIET_DAY and journey.visits_last_7d == 0,
        "note": journey.note,
    }


def _milestone_dict(m: Milestone, progress: OnboardingMilestoneProgress | None, current_day: int) -> dict:
    status = "locked" if m.day > current_day else "pending"
    completed = progress is not None and progress.status == MilestoneStatus.COMPLETED
    if completed:
        status = "completed"
    elif progress is not None and progress.status == MilestoneStatus.SKIPPED:
        status = "skipped"
    return {
        "day": m.day,
        "code": m.code,
        "title": m.title,
        "member_action": m.member_action,
        "staff_action": m.staff_action,
        "status": status,
        "completed_at": progress.completed_at if progress else None,
        "notes": progress.notes if progress else None,
    }


async def member_journey_payload(
    session: AsyncSession, *, org_id: str, member_id: str
) -> dict:
    journey = await _get_journey(session, org_id, member_id)
    if journey is None:
        raise HTTPException(status_code=404, detail="This member has no onboarding journey.")
    member = await session.get(OrganizationMember, member_id)
    user = await session.get(User, member.user_id) if member else None
    name = None
    if member:
        name = member.display_name or (user.full_name if user else None) or (user.email if user else None)
    progress_rows = {
        p.code: p
        for p in (
            await session.execute(
                select(OnboardingMilestoneProgress).where(
                    OnboardingMilestoneProgress.journey_id == journey.id
                )
            )
        ).scalars().all()
    }
    data = _journey_dict(journey, member_name=name)
    data["milestones"] = [
        _milestone_dict(m, progress_rows.get(m.code), journey.current_day) for m in CATALOG
    ]
    return data


async def list_journeys(session: AsyncSession, *, org_id: str, limit: int = 200) -> list[dict]:
    rows = (
        await session.execute(
            select(OnboardingJourney, OrganizationMember, User)
            .join(OrganizationMember, OrganizationMember.id == OnboardingJourney.member_id)
            .outerjoin(User, User.id == OrganizationMember.user_id)
            .where(OnboardingJourney.organization_id == org_id)
            .order_by(OnboardingJourney.current_day.desc(), OnboardingJourney.created_at.desc())
            .limit(max(1, min(limit, 500)))
        )
    ).all()
    out: list[dict] = []
    for journey, member, user in rows:
        name = member.display_name or (user.full_name if user else None) or (user.email if user else None)
        out.append(_journey_dict(journey, member_name=name))
    return out


async def journey_summary(session: AsyncSession, *, org_id: str) -> dict:
    rows = (
        await session.execute(
            select(OnboardingJourney).where(OnboardingJourney.organization_id == org_id)
        )
    ).scalars().all()
    active = [j for j in rows if j.status == OnboardingStatus.ACTIVE]
    return {
        "total": len(rows),
        "active": len(active),
        "completed": sum(1 for j in rows if j.status == OnboardingStatus.COMPLETED),
        "paused": sum(1 for j in rows if j.status == OnboardingStatus.PAUSED),
        "at_risk": sum(1 for j in active if j.current_day >= _QUIET_DAY and j.visits_last_7d == 0),
    }
