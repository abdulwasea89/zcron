"""Retention intelligence: attendance-drop detection + churn-risk scoring.

Two related signals over the attendance stream (Section 1.3, #33/#34):

* **Attendance drop vs own baseline** (#33). A member's *own* recent routine is
  the fairest yardstick: a 5x/week regular who drops to once a week is a far
  stronger signal than someone who was always once a week. We compare the last
  14 days against their prior 8 weeks and flag a halving (or worse).

* **Churn-risk score with reasons** (#34). The drop is one input among several —
  days since last visit, membership status, payment overdue, and a new member
  who never got off the ground. The result is a 0..100 score, a band, and the
  human-readable reasons behind it, so an owner can act instead of staring at a
  number.

Everything is org-scoped and computed from batched queries so the whole roster
scores without an N+1.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.constants import MemberStatus, PaymentStatus, SubscriptionStatus
from app.core.security import now_utc
from app.models.attendance import Attendance
from app.models.audit_log import AuditLog
from app.models.membership import OrganizationMember
from app.models.onboarding import OnboardingJourney
from app.models.payment import Payment
from app.models.subscription import Subscription
from app.models.user import User

# ---- tuning (documented so they are easy to defend / adjust) ----
RECENT_DAYS = 14          # the "now" window
BASELINE_DAYS = 56        # the "usual routine" window, immediately before recent
MIN_TENURE_DAYS = 21      # too new to have a baseline
MIN_BASELINE_WEEKLY = 1.0  # need at least ~1 visit/week historically to compare
DROP_RATIO = 0.5          # recent >= half of baseline is "normal"
SEVERE_RATIO = 0.25       # quarter or worse is "severe"

# Churn risk is only meaningful for members who can still be saved.
_RISK_STATUSES = {
    MemberStatus.ACTIVE,
    MemberStatus.GRACE,
    MemberStatus.FROZEN,
    MemberStatus.EXPIRED,
}

HIGH_BAND = 70
MEDIUM_BAND = 40


@dataclass
class MemberFacts:
    member_id: str
    name: str | None
    status: MemberStatus
    joined_at: datetime | None
    first_visit_at: datetime | None
    last_visit_at: datetime | None
    recent_visits: int
    baseline_visits: int
    overdue: bool                       # grace/expired subscription
    journey_day: int | None = None
    journey_visits_7d: int | None = None


@dataclass
class AttendanceTrend:
    """The #33 result: is this member below their own baseline?"""

    eligible: bool
    baseline_weekly: float
    recent_weekly: float
    drop_ratio: float | None
    is_drop: bool
    severity: str | None                # silent | severe | moderate
    recent_visits: int
    baseline_visits: int
    days_since_last_visit: int | None


@dataclass
class RiskReason:
    code: str
    label: str
    weight: int


@dataclass
class MemberRisk:
    member_id: str
    name: str | None
    status: str
    score: int
    band: str                           # high | medium | low
    trend: AttendanceTrend
    reasons: list[RiskReason] = field(default_factory=list)
    days_since_last_visit: int | None = None
    recent_weekly: float = 0.0
    baseline_weekly: float = 0.0


# --------------------------------------------------------------------- helpers
def _band(score: int) -> str:
    if score >= HIGH_BAND:
        return "high"
    if score >= MEDIUM_BAND:
        return "medium"
    return "low"


def _status_value(status: MemberStatus | str) -> str:
    return status.value if hasattr(status, "value") else str(status)


def compute_trend(facts: MemberFacts, *, now: datetime | None = None) -> AttendanceTrend:
    """Turn raw visit counts into an attendance-drop read (pure)."""

    now = now or now_utc()
    tenure_start = facts.joined_at or facts.first_visit_at
    tenure_days = (now - tenure_start).days if tenure_start else 0

    baseline_weekly = round(facts.baseline_visits / (BASELINE_DAYS / 7), 2)
    recent_weekly = round(facts.recent_visits / (RECENT_DAYS / 7), 2)

    eligible = tenure_days >= MIN_TENURE_DAYS and baseline_weekly >= MIN_BASELINE_WEEKLY
    drop_ratio: float | None = None
    if baseline_weekly > 0:
        drop_ratio = round(recent_weekly / baseline_weekly, 2)

    is_drop = eligible and drop_ratio is not None and drop_ratio <= DROP_RATIO
    severity: str | None = None
    if is_drop:
        if facts.recent_visits == 0:
            severity = "silent"
        elif drop_ratio is not None and drop_ratio <= SEVERE_RATIO:
            severity = "severe"
        else:
            severity = "moderate"

    days_since = None
    if facts.last_visit_at is not None:
        days_since = (now - facts.last_visit_at).days
    elif facts.joined_at is not None:
        days_since = (now - facts.joined_at).days

    return AttendanceTrend(
        eligible=eligible,
        baseline_weekly=baseline_weekly,
        recent_weekly=recent_weekly,
        drop_ratio=drop_ratio,
        is_drop=is_drop,
        severity=severity,
        recent_visits=facts.recent_visits,
        baseline_visits=facts.baseline_visits,
        days_since_last_visit=days_since,
    )


def compute_risk(facts: MemberFacts, *, now: datetime | None = None) -> MemberRisk:
    """Score a member 0..100 with reasons (pure)."""

    now = now or now_utc()
    trend = compute_trend(facts, now=now)
    reasons: list[RiskReason] = []
    score = 0

    # 1. Attendance drop vs their own baseline (#33) — the strongest behavioural
    #    signal because it is personal, not a fixed threshold.
    if trend.is_drop:
        if trend.severity in ("silent", "severe"):
            reasons.append(RiskReason("attendance_drop", "Attendance has dropped sharply versus their own usual routine", 40))
            score += 40
        else:
            reasons.append(RiskReason("attendance_dip", "Attendance is trending below their usual routine", 25))
            score += 25

    # 2. Absolute dormancy — nothing at all for a while.
    days_since = trend.days_since_last_visit
    if facts.first_visit_at is None and facts.joined_at is not None and (days_since or 0) >= 7:
        reasons.append(RiskReason("never_visited", "Has never checked in since joining", 20))
        score += 20
    elif days_since is not None:
        if days_since >= 30:
            reasons.append(RiskReason("dormant_30", "No visit in 30+ days", 30))
            score += 30
        elif days_since >= 21:
            reasons.append(RiskReason("dormant_21", "No visit in 3 weeks", 25))
            score += 25
        elif days_since >= 14:
            reasons.append(RiskReason("dormant_14", "No visit in 14 days", 18))
            score += 18
        elif days_since >= 7:
            reasons.append(RiskReason("dormant_7", "No visit in a week", 10))
            score += 10

    # 3. Membership / money state.
    if facts.status == MemberStatus.EXPIRED:
        reasons.append(RiskReason("expired", "Membership has expired", 30))
        score += 30
    elif facts.status == MemberStatus.GRACE:
        reasons.append(RiskReason("grace", "Payment is overdue (in grace)", 20))
        score += 20
    elif facts.status == MemberStatus.FROZEN:
        reasons.append(RiskReason("frozen", "Membership is frozen", 10))
        score += 10

    # 4. New member who never built the habit (onboarding journey).
    if (
        facts.journey_day is not None
        and facts.journey_day >= 7
        and (facts.journey_visits_7d or 0) == 0
    ):
        reasons.append(RiskReason("onboarding_stall", "New member with no visits in week one", 15))
        score += 15

    # 5. Loyalty cushion: a long-tenured member still showing up is low risk.
    tenure_start = facts.joined_at or facts.first_visit_at
    tenure_days = (now - tenure_start).days if tenure_start else 0
    if tenure_days > 180 and days_since is not None and days_since < 14:
        score -= 10

    score = max(0, min(100, score))
    return MemberRisk(
        member_id=facts.member_id,
        name=facts.name,
        status=_status_value(facts.status),
        score=score,
        band=_band(score),
        trend=trend,
        reasons=reasons,
        days_since_last_visit=days_since,
        recent_weekly=trend.recent_weekly,
        baseline_weekly=trend.baseline_weekly,
    )


# --------------------------------------------------------------------- loading
async def _facts(
    session: AsyncSession, *, org_id: str, member_ids: list[str] | None = None
) -> list[MemberFacts]:
    """Load everything needed to score, in batched queries."""

    now = now_utc()
    recent_start = now - timedelta(days=RECENT_DAYS)
    baseline_start = now - timedelta(days=RECENT_DAYS + BASELINE_DAYS)

    stmt = (
        select(OrganizationMember, User)
        .join(User, User.id == OrganizationMember.user_id)
        .where(
            OrganizationMember.organization_id == org_id,
            OrganizationMember.role == "member",
            OrganizationMember.member_status.in_(list(_RISK_STATUSES)),
        )
    )
    if member_ids is not None:
        stmt = stmt.where(OrganizationMember.id.in_(member_ids))
    rows = (await session.execute(stmt)).all()
    ids = [m.id for m, _u in rows]
    if not ids:
        return []

    # Visit aggregates (one query): min/max over all time + windowed counts.
    agg = {
        mid: {"first": None, "last": None, "recent": 0, "baseline": 0}
        for mid in ids
    }
    visit_rows = (
        await session.execute(
            select(Attendance.member_id, Attendance.checked_in_at).where(
                Attendance.organization_id == org_id,
                Attendance.member_id.in_(ids),
            )
        )
    ).all()
    for mid, at in visit_rows:
        bucket = agg.get(mid)
        if bucket is None:
            continue
        if bucket["first"] is None or at < bucket["first"]:
            bucket["first"] = at
        if bucket["last"] is None or at > bucket["last"]:
            bucket["last"] = at
        if at >= recent_start:
            bucket["recent"] += 1
        elif at >= baseline_start:
            bucket["baseline"] += 1

    overdue_ids = {
        s.member_id
        for s in (
            await session.execute(
                select(Subscription).where(
                    Subscription.organization_id == org_id,
                    Subscription.member_id.in_(ids),
                    Subscription.status.in_([SubscriptionStatus.GRACE, SubscriptionStatus.EXPIRED]),
                )
            )
        ).scalars().all()
    }
    journeys = {
        j.member_id: j
        for j in (
            await session.execute(
                select(OnboardingJourney).where(
                    OnboardingJourney.organization_id == org_id,
                    OnboardingJourney.member_id.in_(ids),
                )
            )
        ).scalars().all()
    }

    facts: list[MemberFacts] = []
    for m, u in rows:
        a = agg[m.id]
        j = journeys.get(m.id)
        facts.append(
            MemberFacts(
                member_id=m.id,
                name=m.display_name or (u.full_name if u else None) or (u.email if u else None),
                status=m.member_status,
                joined_at=m.joined_at,
                first_visit_at=a["first"],
                last_visit_at=a["last"],
                recent_visits=a["recent"],
                baseline_visits=a["baseline"],
                overdue=m.id in overdue_ids,
                journey_day=j.current_day if j else None,
                journey_visits_7d=j.visits_last_7d if j else None,
            )
        )
    return facts


# --------------------------------------------------------------------- public
async def risk_roster(
    session: AsyncSession, *, org_id: str, min_score: int = 1, limit: int = 100
) -> list[MemberRisk]:
    """Every at-risk member, highest score first."""

    facts = await _facts(session, org_id=org_id)
    risks = [compute_risk(f) for f in facts]
    risks = [r for r in risks if r.score >= min_score]
    risks.sort(key=lambda r: (-r.score, r.name or ""))
    return risks[: max(1, min(limit, 500))]


async def attendance_drops(
    session: AsyncSession, *, org_id: str, limit: int = 100
) -> list[MemberRisk]:
    """Members trending below their own baseline (#33), worst drop first."""

    facts = await _facts(session, org_id=org_id)
    risks = [compute_risk(f) for f in facts if compute_trend(f).is_drop]
    risks.sort(key=lambda r: (r.trend.drop_ratio if r.trend.drop_ratio is not None else 1.0))
    return risks[: max(1, min(limit, 500))]


async def member_risk(session: AsyncSession, *, org_id: str, member_id: str) -> MemberRisk:
    member = await session.get(OrganizationMember, member_id)
    if member is None or member.organization_id != org_id:
        raise HTTPException(status_code=404, detail="Member not found in this organization.")
    facts = await _facts(session, org_id=org_id, member_ids=[member_id])
    if not facts:
        raise HTTPException(status_code=404, detail="Member not found in this organization.")
    return compute_risk(facts[0])


async def retention_summary(session: AsyncSession, *, org_id: str) -> dict:
    """Headline retention numbers for the owner command centre."""

    risks = await risk_roster(session, org_id=org_id, min_score=0, limit=500)
    drops = [r for r in risks if r.trend.is_drop]
    at_risk_ids = [r.member_id for r in risks if r.band in ("high", "medium")]

    revenue_at_risk = 0.0
    if at_risk_ids:
        subs = (
            await session.execute(
                select(Subscription)
                .where(
                    Subscription.organization_id == org_id,
                    Subscription.member_id.in_(at_risk_ids),
                )
                .order_by(Subscription.created_at.desc())
            )
        ).scalars().all()
        seen: set[str] = set()
        for s in subs:  # newest first -> count each member once
            if s.member_id in seen:
                continue
            seen.add(s.member_id)
            revenue_at_risk += s.price_snapshot or 0.0

    return {
        "scored": len(risks),
        "high": sum(1 for r in risks if r.band == "high"),
        "medium": sum(1 for r in risks if r.band == "medium"),
        "low": sum(1 for r in risks if r.band == "low"),
        "attendance_drops": len(drops),
        "silent": sum(1 for r in drops if r.trend.severity == "silent"),
        "revenue_at_risk": round(revenue_at_risk, 2),
    }


async def recovered_renewals(session: AsyncSession, *, org_id: str, limit: int = 10) -> list[dict]:
    rows = (await session.execute(
        select(AuditLog.created_at, Payment, OrganizationMember.display_name)
        .join(Payment, Payment.id == AuditLog.entity_id)
        .outerjoin(OrganizationMember, OrganizationMember.id == Payment.member_id)
        .where(
            AuditLog.organization_id == org_id,
            AuditLog.action == "member.renewal_recovered",
            AuditLog.entity_type == "payment",
            Payment.organization_id == org_id,
            Payment.status.in_([PaymentStatus.SUCCEEDED, PaymentStatus.PARTIALLY_REFUNDED]),
        )
        .order_by(AuditLog.created_at.desc())
        .limit(100)
    )).all()
    return [
        {"payment_id": payment.id, "member_id": payment.member_id,
         "member_name": member_name or "Member", "amount": round(payment.amount - payment.refunded_amount, 2),
         "currency": payment.currency, "recovered_at": recovered_at}
        for recovered_at, payment, member_name in rows
        if payment.amount > payment.refunded_amount
    ][:limit]
