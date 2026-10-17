"""SaaS subscription lifecycle (Section 3.2).

Upgrade (immediate, prorated), downgrade (next cycle, blocked if usage exceeds
the lower cap), cancellation (runs to period end), and the failed-charge
lifecycle: past_due -> read_only (grace ended) -> suspended -> archived.
Platform Stripe only (Security Rule #3) — never member money.
"""

from __future__ import annotations

from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.constants import (
    TIER_MEMBER_CAP,
    MemberStatus,
    PaymentKind,
    SaasStatus,
    SaasTier,
)
from app.core.security import now_utc
from app.integrations.email import send_email_safe as send_email
from app.integrations.push import send_push
from app.models.membership import OrganizationMember
from app.models.organization import Organization
from app.models.payment import Payment
from app.models.user import User
from app.realtime import events
from app.services.audit_service import record_audit
from app.utils.pdf import render_invoice_pdf

# Read-only once SaaS grace ends; full lockout / archive later (Section 3.2.4).
GRACE_DAYS = 6
SUSPEND_AFTER_DAYS = 30       # days in READ_ONLY before SUSPENDED
ARCHIVE_AFTER_DAYS = 90       # days in SUSPENDED before ARCHIVED


async def _member_count(session: AsyncSession, org_id: str) -> int:
    return int(
        (
            await session.execute(
                select(func.count()).select_from(OrganizationMember).where(
                    OrganizationMember.organization_id == org_id,
                    OrganizationMember.role == "member",
                    OrganizationMember.member_status.in_(
                        [MemberStatus.ACTIVE, MemberStatus.GRACE, MemberStatus.FROZEN]
                    ),
                )
            )
        ).scalar_one()
        or 0
    )


async def status(session: AsyncSession, *, org: Organization) -> dict:
    count = await _member_count(session, org.id)
    return {
        "saas_tier": org.saas_tier.value,
        "saas_status": org.saas_status.value,
        "member_cap": org.member_cap,
        "current_member_count": count,
        "current_period_end": org.saas_current_period_end,
        "grace_until": org.saas_grace_until,
        # Cancellation ends billing; it must not disable reads/profile access.
        "read_only": org.saas_status in {SaasStatus.READ_ONLY, SaasStatus.SUSPENDED},
        "retry_count": org.saas_retry_count,
        "state_changed_at": org.saas_state_changed_at,
    }


async def upgrade(session: AsyncSession, *, org: Organization, tier: SaasTier, actor_id: str) -> Organization:
    """Immediate, prorated upgrade (Section 3.2.5). New features unlock instantly."""

    order = {SaasTier.STARTER: 0, SaasTier.PRO: 1, SaasTier.ENTERPRISE: 2}
    if order[tier] <= order[org.saas_tier]:
        raise HTTPException(status_code=409, detail="Use downgrade for same/lower tier.")
    org.saas_tier = tier
    org.member_cap = TIER_MEMBER_CAP[tier]
    if tier == SaasTier.ENTERPRISE:
        org.mfa_required = True
    session.add(org)
    await record_audit(session, action="saas.upgraded", organization_id=org.id, actor_user_id=actor_id,
                       entity_type="organization", entity_id=org.id, new_values={"tier": tier.value})
    return org


async def downgrade(session: AsyncSession, *, org: Organization, tier: SaasTier, actor_id: str) -> Organization:
    """Scheduled downgrade — blocked if current usage exceeds the lower cap (Section 3.2.6).

    Applied immediately here for simplicity; production schedules it for the next
    cycle. The cap guard is the important business rule.
    """

    order = {SaasTier.STARTER: 0, SaasTier.PRO: 1, SaasTier.ENTERPRISE: 2}
    if order[tier] >= order[org.saas_tier]:
        raise HTTPException(status_code=409, detail="Use upgrade for same/higher tier.")
    new_cap = TIER_MEMBER_CAP[tier]
    if new_cap is not None:
        count = await _member_count(session, org.id)
        if count > new_cap:
            raise HTTPException(
                status_code=409,
                detail=f"Reduce members to {new_cap} before downgrading (currently {count}).",
            )
    org.saas_tier = tier
    org.member_cap = new_cap
    session.add(org)
    await record_audit(session, action="saas.downgraded", organization_id=org.id, actor_user_id=actor_id,
                       entity_type="organization", entity_id=org.id, new_values={"tier": tier.value})
    return org


async def cancel(session: AsyncSession, *, org: Organization, actor_id: str) -> Organization:
    """Cancel — runs to end of paid period, then archived after retention (Section 3.2.7)."""

    org.saas_status = SaasStatus.CANCELLED
    org.saas_retry_count = 0
    org.saas_state_changed_at = now_utc()
    session.add(org)
    await record_audit(session, action="saas.cancelled", organization_id=org.id, actor_user_id=actor_id,
                       entity_type="organization", entity_id=org.id)
    return org


async def list_invoices(session: AsyncSession, *, org_id: str) -> list[Payment]:
    return list(
        (
            await session.execute(
                select(Payment).where(
                    Payment.organization_id == org_id,
                    Payment.kind == PaymentKind.SAAS_SUBSCRIPTION,
                ).order_by(Payment.created_at.desc())
            )
        ).scalars()
    )


async def get_invoice_pdf(session: AsyncSession, *, invoice_id: str, org: Organization) -> bytes:
    payment = (
        await session.execute(
            select(Payment).where(
                Payment.id == invoice_id,
                Payment.organization_id == org.id,
                Payment.kind == PaymentKind.SAAS_SUBSCRIPTION,
            )
        )
    ).scalar_one_or_none()

    if payment is None:
        raise HTTPException(status_code=404, detail="Invoice not found")

    subtotal = (payment.amount or 0.0) - (payment.tax_amount or 0.0)
    tier_name = org.saas_tier.value.title() if org.saas_tier else "Subscription"
    period = (
        org.saas_current_period_end.strftime("%b %Y")
        if org.saas_current_period_end
        else ""
    )
    description = f"{tier_name} Plan{f' — {period}' if period else ''}"

    return render_invoice_pdf(
        gym_name=org.name,
        gym_address=org.address,
        invoice_id=payment.id[:12],
        invoice_date=payment.paid_at.strftime("%b %d, %Y") if payment.paid_at else payment.created_at.strftime("%b %d, %Y"),
        status=payment.status.value if hasattr(payment.status, "value") else str(payment.status),
        description=description,
        subtotal=subtotal,
        tax=payment.tax_amount or 0.0,
        total=payment.amount or 0.0,
        currency=payment.currency or "USD",
    )


# ----------------------------------------------- failed-charge lifecycle
async def _notify_owner(
    session: AsyncSession, *, org: Organization, kind: str,
) -> None:
    """Send email+push to the owner about a failed-charge event."""

    owner = await _owner_user(session, org.id)
    if owner is None:
        return
    days_left = max(0, GRACE_DAYS - (org.saas_retry_count or 0))
    if kind == "first_failure":
        await send_email(
            owner.email, f"SaaS Payment Failed — {org.name}",
            f"Your subscription payment for {org.name} failed.\n"
            f"Update your card in Settings → Billing; you have {GRACE_DAYS} days before "
            f"the account becomes read-only.\n"
            f"Grace period ends: {org.saas_grace_until}.",
        )
        await send_push(
            None, "Payment failed",
            f"Update billing — {GRACE_DAYS} days of access left.",
        )
    else:
        n = org.saas_retry_count
        await send_email(
            owner.email, f"SaaS Payment Retry #{n} Failed — {org.name}",
            f"Stripe retry #{n} failed. You have approximately {days_left} days "
            f"until read-only mode. Update your card in Settings → Billing.",
        )
        await send_push(
            None, f"Retry #{n} failed",
            f"Update billing — {days_left} days left.",
        )


async def handle_failed_charge(session: AsyncSession, *, org: Organization) -> Organization:
    """Handle a SaaS payment-failure webhook (Section 3.2.4).

    First failure (``ACTIVE → PAST_DUE``):
        sets grace_until = now + 6 days, notifies owner.

    Subsequent failures (Stripe retries):
        increments ``saas_retry_count``, notifies owner, does NOT reset grace_until.
    """

    now = now_utc()
    if org.saas_status == SaasStatus.ACTIVE:
        # First failure — begin the grace workflow.
        org.saas_status = SaasStatus.PAST_DUE
        org.saas_grace_until = now + timedelta(days=GRACE_DAYS)
        org.saas_retry_count = 0
        org.saas_state_changed_at = now
        session.add(org)
        await _notify_owner(session, org=org, kind="first_failure")
        await record_audit(session, action="saas.payment_failed",
                           organization_id=org.id, entity_type="organization", entity_id=org.id,
                           new_values={"status": org.saas_status.value, "grace_until": str(org.saas_grace_until)})
    else:
        # Stripe retry failed — increment counter, notify, keep existing grace_until.
        org.saas_retry_count = (org.saas_retry_count or 0) + 1
        session.add(org)
        await _notify_owner(session, org=org, kind="retry_failure")
        await record_audit(session, action="saas.retry_failed",
                           organization_id=org.id, entity_type="organization", entity_id=org.id,
                           new_values={"retry_count": org.saas_retry_count})

    await events.publish(org.id, "saas.payment_failed", {
        "status": org.saas_status.value,
        "retry_count": org.saas_retry_count,
        "grace_until": org.saas_grace_until.isoformat() if org.saas_grace_until else None,
    })
    return org


async def _archive_org_data(session: AsyncSession, *, org: Organization) -> None:
    """Anonymize sensitive data when an org is archived (Day 90, Section 3.2.8)."""

    org.name = f"[Archived] {org.name}"
    org.address = None
    org.logo_url = None
    org.accent_color = None
    org.working_hours = None
    org.org_code = f"archived-{org.id[:8]}"
    session.add(org)

    members = (
        await session.execute(
            select(OrganizationMember).where(OrganizationMember.organization_id == org.id)
        )
    ).scalars().all()
    for m in members:
        m.phone = None
        m.emergency_contact = None
        m.photo_url = None
        m.goals = None
        m.health_notes = None
        m.id_document_type = None
        m.id_document_last4 = None

    await record_audit(session, action="saas.archived",
                       organization_id=org.id, entity_type="organization", entity_id=org.id)


async def enforce_lifecycle(session: AsyncSession, *, org: Organization) -> Organization:
    """Advance an org through the failed-charge lifecycle.

    Called hourly by the billing worker (celery_app.py). Transition timeline:

        PAST_DUE + grace_until passed  →  READ_ONLY  (day 6)
        READ_ONLY + 30 days            →  SUSPENDED  (day 30)
        SUSPENDED + 90 days            →  ARCHIVED   (day 90)
    """

    now = now_utc()
    changed = False

    if org.saas_status == SaasStatus.PAST_DUE and org.saas_grace_until and org.saas_grace_until < now:
        org.saas_status = SaasStatus.READ_ONLY
        org.saas_state_changed_at = now
        changed = True
        await record_audit(session, action="saas.read_only",
                           organization_id=org.id, entity_type="organization", entity_id=org.id,
                           new_values={"status": "read_only"})

    elif org.saas_status == SaasStatus.READ_ONLY and org.saas_state_changed_at and (
        now - org.saas_state_changed_at
    ).days >= SUSPEND_AFTER_DAYS:
        org.saas_status = SaasStatus.SUSPENDED
        org.saas_state_changed_at = now
        changed = True
        await record_audit(session, action="saas.suspended",
                           organization_id=org.id, entity_type="organization", entity_id=org.id,
                           new_values={"status": "suspended"})

    elif org.saas_status == SaasStatus.SUSPENDED and org.saas_state_changed_at and (
        now - org.saas_state_changed_at
    ).days >= ARCHIVE_AFTER_DAYS:
        org.saas_status = SaasStatus.ARCHIVED
        org.saas_state_changed_at = now
        changed = True
        await _archive_org_data(session, org=org)
        await record_audit(session, action="saas.archived",
                           organization_id=org.id, entity_type="organization", entity_id=org.id,
                           new_values={"status": "archived"})

    if changed:
        session.add(org)
        await events.publish(org.id, "saas.status_changed", {"status": org.saas_status.value})

    return org


async def _owner_user(session: AsyncSession, org_id: str) -> User | None:
    return (
        await session.execute(
            select(User).join(OrganizationMember, OrganizationMember.user_id == User.id).where(
                OrganizationMember.organization_id == org_id,
                OrganizationMember.role == "owner",
            )
        )
    ).scalars().first()
