"""Win-back: re-engaging lapsed members (#36).

A member who expired or cancelled is not necessarily gone — a well-timed,
respectful offer recovers a meaningful share of them. This service lists who has
lapsed, runs a campaign that sends the offer (with a cooldown so nobody is
pestered), and records recovery when the member reactivates — turning win-back
into a measurable "money recovered" number (the seed of the Wins feed, #67).
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.constants import MemberStatus, NotificationKind, WinBackStatus
from app.core.security import now_utc
from app.integrations.email import send_email_safe as send_email
from app.models.attendance import Attendance
from app.models.membership import OrganizationMember
from app.models.organization import Organization
from app.models.user import User
from app.models.winback import WinBackAttempt
from app.services.audit_service import record_audit

LAPSED_STATUSES = {MemberStatus.EXPIRED, MemberStatus.CANCELLED}
DEFAULT_COOLDOWN_DAYS = 30


def _name(member: OrganizationMember, user: User | None) -> str:
    return member.display_name or (user.full_name if user else None) or (user.email if user else None) or "there"


async def _latest_attempts(session: AsyncSession, *, org_id: str, member_ids: list[str]) -> dict[str, WinBackAttempt]:
    if not member_ids:
        return {}
    rows = (
        await session.execute(
            select(WinBackAttempt)
            .where(
                WinBackAttempt.organization_id == org_id,
                WinBackAttempt.member_id.in_(member_ids),
            )
            .order_by(WinBackAttempt.contacted_at.desc())
        )
    ).scalars().all()
    out: dict[str, WinBackAttempt] = {}
    for a in rows:
        out.setdefault(a.member_id, a)  # newest first
    return out


async def lapsed_members(session: AsyncSession, *, org_id: str, limit: int = 200) -> list[dict]:
    """Expired / cancelled members with their last-visit and last-outreach info."""

    rows = (
        await session.execute(
            select(OrganizationMember, User)
            .join(User, User.id == OrganizationMember.user_id)
            .where(
                OrganizationMember.organization_id == org_id,
                OrganizationMember.role == "member",
                OrganizationMember.member_status.in_(list(LAPSED_STATUSES)),
            )
            .order_by(OrganizationMember.updated_at.desc())
            .limit(max(1, min(limit, 500)))
        )
    ).all()
    ids = [m.id for m, _u in rows]
    last_visits = dict(
        (
            await session.execute(
                select(Attendance.member_id, func.max(Attendance.checked_in_at))
                .where(Attendance.organization_id == org_id, Attendance.member_id.in_(ids))
                .group_by(Attendance.member_id)
            )
        ).all()
    )
    attempts = await _latest_attempts(session, org_id=org_id, member_ids=ids)

    now = now_utc()
    out: list[dict] = []
    for member, user in rows:
        last = last_visits.get(member.id)
        attempt = attempts.get(member.id)
        out.append({
            "member_id": member.id,
            "name": _name(member, user),
            "email": user.email,
            "status": member.member_status.value if hasattr(member.member_status, "value") else str(member.member_status),
            "last_visit_at": last,
            "days_since_last_visit": (now - last).days if last else None,
            "win_back_status": attempt.status.value if attempt and hasattr(attempt.status, "value") else (str(attempt.status) if attempt else None),
            "contacted_at": attempt.contacted_at if attempt else None,
            "can_contact": attempt is None or attempt.status == WinBackStatus.LOST or (
                attempt.status == WinBackStatus.CONTACTED
                and attempt.contacted_at < now - timedelta(days=DEFAULT_COOLDOWN_DAYS)
            ),
        })
    return out


async def run_campaign(
    session: AsyncSession,
    *,
    org_id: str,
    actor_user_id: str | None = None,
    offer_text: str | None = None,
    cooldown_days: int = DEFAULT_COOLDOWN_DAYS,
    limit: int = 200,
) -> dict:
    """Send the win-back offer to lapsed members not contacted recently."""

    org = await session.get(Organization, org_id)
    if org is None:
        return {"targeted": 0, "sent": 0}

    lapsed = await lapsed_members(session, org_id=org_id, limit=limit)
    now = now_utc()
    cutoff = now - timedelta(days=cooldown_days)
    offer = offer_text or f"We'd love to have you back at {org.name}. Rejoin this week and your next session is on us."

    attempts = await _latest_attempts(
        session, org_id=org_id, member_ids=[e["member_id"] for e in lapsed]
    )
    sent = 0
    for entry in lapsed:
        attempt = attempts.get(entry["member_id"])
        if attempt is not None:
            if attempt.status == WinBackStatus.RECOVERED:
                continue
            if attempt.status == WinBackStatus.CONTACTED and attempt.contacted_at >= cutoff:
                continue  # cooldown

        session.add(
            WinBackAttempt(
                organization_id=org_id,
                member_id=entry["member_id"],
                status=WinBackStatus.CONTACTED,
                offer_text=offer,
                channel="email",
                contacted_at=now,
            )
        )
        await send_email(entry["email"], f"We miss you at {org.name}", offer)

        from app.services.notifications_service import create_notification

        member = await session.get(OrganizationMember, entry["member_id"])
        if member is not None:
            await create_notification(
                session,
                org_id=org_id,
                recipient_user_id=member.user_id,
                category=NotificationKind.WINBACK,
                title=f"Come back to {org.name}",
                body=offer,
                data={"offer": offer},
            )
        sent += 1

    if sent:
        await session.flush()
        await record_audit(
            session,
            action="winback.campaign_run",
            organization_id=org_id,
            actor_user_id=actor_user_id,
            entity_type="organization",
            entity_id=org_id,
            metadata={"sent": sent},
        )
    return {"targeted": len(lapsed), "sent": sent}


async def mark_recovered(
    session: AsyncSession, *, org_id: str, member_id: str, amount: float | None = None
) -> bool:
    """Resolve a member's latest open win-back when they reactivate."""

    attempt = (
        await session.execute(
            select(WinBackAttempt)
            .where(
                WinBackAttempt.organization_id == org_id,
                WinBackAttempt.member_id == member_id,
                WinBackAttempt.status == WinBackStatus.CONTACTED,
            )
            .order_by(WinBackAttempt.contacted_at.desc())
        )
    ).scalars().first()
    if attempt is None:
        return False
    attempt.status = WinBackStatus.RECOVERED
    attempt.recovered_at = now_utc()
    attempt.recovered_amount = amount
    session.add(attempt)
    await record_audit(
        session,
        action="winback.recovered",
        organization_id=org_id,
        actor_user_id=None,
        entity_type="member",
        entity_id=member_id,
        metadata={"amount": amount},
    )
    return True


async def close_attempt(
    session: AsyncSession, *, org_id: str, member_id: str, actor_user_id: str | None = None
) -> bool:
    """Mark a member's open outreach lost (manual)."""

    attempt = (
        await session.execute(
            select(WinBackAttempt)
            .where(
                WinBackAttempt.organization_id == org_id,
                WinBackAttempt.member_id == member_id,
                WinBackAttempt.status == WinBackStatus.CONTACTED,
            )
            .order_by(WinBackAttempt.contacted_at.desc())
        )
    ).scalars().first()
    if attempt is None:
        return False
    attempt.status = WinBackStatus.LOST
    session.add(attempt)
    await record_audit(
        session,
        action="winback.lost",
        organization_id=org_id,
        actor_user_id=actor_user_id,
        entity_type="member",
        entity_id=member_id,
    )
    return True


async def summary(session: AsyncSession, *, org_id: str) -> dict:
    """Win-back performance: contacted, recovered, revenue won back."""

    attempts = list(
        (
            await session.execute(
                select(WinBackAttempt).where(WinBackAttempt.organization_id == org_id)
            )
        ).scalars().all()
    )
    contacted = len(attempts)
    recovered = [a for a in attempts if a.status == WinBackStatus.RECOVERED]
    return {
        "lapsed": len(await lapsed_members(session, org_id=org_id, limit=500)),
        "contacted": contacted,
        "recovered": len(recovered),
        "recovery_rate": round(len(recovered) / contacted, 3) if contacted else 0.0,
        "recovered_revenue": round(sum(a.recovered_amount or 0.0 for a in recovered), 2),
    }
