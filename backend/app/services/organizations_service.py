"""Organization provisioning & settings service (Sections 3, 4, 7).

Owner registration completion: charges the first SaaS month via the Platform
Stripe account, then provisions the Organization (unique org code), the owner's
OrganizationMember row, and a first auth session. Also exposes the setup
checklist and enrollment/gym-status/Connect operations.
"""

from __future__ import annotations

from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.constants import (
    ConnectStatus,
    MemberStatus,
    Role,
    SaasStatus,
    SaasTier,
    TIER_MEMBER_CAP,
    TIER_PRICE_USD,
)
from app.core.industry import CHECKLIST_LABELS, get_industry, public_industry_detail
from app.core.security import now_utc
from app.integrations.email import send_email_safe as send_email
from app.integrations.stripe_client import platform_stripe
from app.integrations.stripe_connect import connect_stripe
from app.models.membership import OrganizationMember
from app.models.organization import Organization
from app.models.session import AuthSession
from app.models.user import User
from app.realtime import events
from app.schemas.organizations import (
    CreateOrganizationRequest,
    RegisterGymRequest,
    SetupChecklist,
)
from app.services import auth_service
from app.services.audit_service import record_audit
from app.utils.org_code import generate_org_code


def _welcome_email(org_name: str, org_code: str, *, industry_key: str, additional: bool = False) -> tuple[str, str]:
    """Subject/body for the post-provisioning welcome email, industry-aware."""
    noun = get_industry(industry_key).key_value  # gym | office | academy
    prefix = "your new" if additional else "your"
    subject = f"Welcome to {prefix} {noun}"
    body = f"Your {noun} '{org_name}' is live. Org code: {org_code}. Log in to finish setup."
    return subject, body


def _industry_code_prefix(industry: str | None) -> str:
    """Org-code word fallback for an industry (OFF/ACAD/etc), default GYM."""
    try:
        return get_industry(industry or "gym").org_code_fallback_prefix
    except KeyError:
        return "GYM"


async def start_owner_onboarding(session: AsyncSession, user: User, *, ip: str | None = None):
    """Create a locked, unpaid workspace so the verified owner can enter setup."""
    existing = (await session.execute(select(OrganizationMember).where(
        OrganizationMember.user_id == user.id,
        OrganizationMember.role == Role.OWNER,
    ))).scalars().first()
    if existing:
        org = await session.get(Organization, existing.organization_id)
        if org:
            access, refresh = await auth_service.create_session(
                session, user=user, org_id=org.id, role=Role.OWNER, ip=ip
            )
            return org, access, refresh

    org = Organization(
        name="Workspace setup", org_code=await _unique_org_code(session, "Workspace setup"),
        industry="gym", saas_tier=SaasTier.STARTER, saas_status=SaasStatus.TRIALING,
        member_cap=TIER_MEMBER_CAP[SaasTier.STARTER], checklist_plan_published=False,
        checklist_enrollment_configured=False,
        onboarding_complete=False,
    )
    session.add(org)
    await session.flush()
    owner = OrganizationMember(
        organization_id=org.id, user_id=user.id, role=Role.OWNER,
        member_status=MemberStatus.PENDING_PAYMENT, joined_at=now_utc(), profile_complete=False,
    )
    session.add(owner)
    await session.flush()
    access, refresh = await auth_service.create_session(
        session, user=user, org_id=org.id, role=Role.OWNER, ip=ip
    )
    return org, access, refresh


async def _unique_org_code(session: AsyncSession, name: str, *, industry: str | None = None) -> str:
    fallback = _industry_code_prefix(industry)
    for _ in range(10):
        code = generate_org_code(name, fallback=fallback)
        exists = (
            await session.execute(select(Organization).where(Organization.org_code == code))
        ).scalar_one_or_none()
        if exists is None:
            return code
    raise HTTPException(status_code=500, detail="Could not generate unique org code.")


async def register_gym(
    session: AsyncSession, data: RegisterGymRequest, *, ip: str | None = None
) -> tuple[Organization, str, str]:
    """Provision an org for a verified owner. Returns (org, access, refresh)."""

    user = (
        await session.execute(select(User).where(User.email == data.owner_email.lower()))
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="Owner account not found.")
    if not user.email_verified:
        raise HTTPException(status_code=403, detail="Verify your email before registering a gym.")

    # ---- SaaS first-month charge (Section 3.2.2) ----
    customer_id = await platform_stripe.create_customer(user.email, user.full_name)
    if data.tier is not SaasTier.ENTERPRISE:
        price = TIER_PRICE_USD[data.tier] or 0
        pi = await platform_stripe.charge_first_month(
            customer_id=customer_id,
            amount_cents=price * 100,
            currency="usd",
            idempotency_key=f"saas-first-{user.id}-{data.tier.value}",
        )
        if pi.status != "succeeded":
            raise HTTPException(status_code=402, detail="SaaS payment failed. Please retry.")
    subscription_id = await platform_stripe.create_subscription(
        customer_id=customer_id, tier=data.tier.value
    )

    # ---- Provision organization ----
    d = data.details
    org = Organization(
        name=d.name,
        org_code=await _unique_org_code(session, d.name, industry=d.industry),
        country=d.country,
        timezone=d.timezone,
        default_currency=d.default_currency,
        address=d.address,
        logo_url=d.logo_url,
        accent_color=d.accent_color,
        working_hours=d.working_hours,
        industry=d.industry,
        saas_tier=data.tier,
        saas_status=SaasStatus.ACTIVE,
        member_cap=TIER_MEMBER_CAP[data.tier],
        stripe_customer_id=customer_id,
        stripe_subscription_id=subscription_id,
        saas_current_period_end=now_utc() + timedelta(days=30),
        mfa_required=(data.tier is SaasTier.ENTERPRISE),
        onboarding_complete=True,
    )
    session.add(org)
    await session.flush()

    # ---- Owner membership ----
    owner_member = OrganizationMember(
        organization_id=org.id,
        user_id=user.id,
        role=Role.OWNER,
        member_status=MemberStatus.ACTIVE,
        joined_at=now_utc(),
        profile_complete=True,
    )
    session.add(owner_member)
    await session.flush()

    await record_audit(
        session, action="org.provisioned", actor_user_id=user.id,
        organization_id=org.id, entity_type="organization", entity_id=org.id,
        new_values={"tier": data.tier.value, "org_code": org.org_code, "industry": org.industry},
        ip_address=ip,
    )
    subject, body = _welcome_email(org.name, org.org_code, industry_key=org.industry)
    await send_email(user.email, subject, body)

    access, refresh = await auth_service.create_session(
        session, user=user, org_id=org.id, role=Role.OWNER, ip=ip
    )
    return org, access, refresh


async def create_organization_for_user(
    session: AsyncSession,
    user: User,
    data: RegisterGymRequest | CreateOrganizationRequest,
    *,
    ip: str | None = None,
) -> tuple[Organization, str, str]:
    """Provision a new org linked to an existing, verified user. Returns (org, access, refresh)."""

    if not user.email_verified:
        raise HTTPException(status_code=403, detail="Verify your email before registering a gym.")

    customer_id = await platform_stripe.create_customer(user.email, user.full_name)
    tier = data.tier
    if tier is not SaasTier.ENTERPRISE:
        price = TIER_PRICE_USD[tier] or 0
        pi = await platform_stripe.charge_first_month(
            customer_id=customer_id,
            amount_cents=price * 100,
            currency="usd",
            idempotency_key=f"saas-create-{user.id}-{tier.value}-{now_utc().timestamp()}",
        )
        if pi.status != "succeeded":
            raise HTTPException(status_code=402, detail="SaaS payment failed. Please retry.")
    subscription_id = await platform_stripe.create_subscription(
        customer_id=customer_id, tier=tier.value
    )

    d = data.details
    org = Organization(
        name=d.name,
        org_code=await _unique_org_code(session, d.name, industry=d.industry),
        country=d.country,
        timezone=d.timezone,
        default_currency=d.default_currency,
        address=d.address,
        logo_url=d.logo_url,
        accent_color=d.accent_color,
        working_hours=d.working_hours,
        industry=d.industry,
        saas_tier=tier,
        saas_status=SaasStatus.ACTIVE,
        member_cap=TIER_MEMBER_CAP[tier],
        stripe_customer_id=customer_id,
        stripe_subscription_id=subscription_id,
        saas_current_period_end=now_utc() + timedelta(days=30),
        mfa_required=(tier is SaasTier.ENTERPRISE),
        onboarding_complete=True,
    )
    session.add(org)
    await session.flush()

    owner_member = OrganizationMember(
        organization_id=org.id,
        user_id=user.id,
        role=Role.OWNER,
        member_status=MemberStatus.ACTIVE,
        joined_at=now_utc(),
        profile_complete=True,
    )
    session.add(owner_member)
    await session.flush()

    await record_audit(
        session, action="org.provisioned", actor_user_id=user.id,
        organization_id=org.id, entity_type="organization", entity_id=org.id,
        new_values={"tier": tier.value, "org_code": org.org_code, "industry": org.industry},
        ip_address=ip,
    )
    subject, body = _welcome_email(org.name, org.org_code, industry_key=org.industry, additional=True)
    await send_email(user.email, subject, body)

    access, refresh = await auth_service.create_session(
        session, user=user, org_id=org.id, role=Role.OWNER, ip=ip
    )
    return org, access, refresh


_CHECKLIST_FLAGS: dict[str, str] = {
    "stripe": "checklist_stripe_connected",
    "offer": "checklist_plan_published",
    "enroll": "checklist_enrollment_configured",
    "staff": "checklist_staff_invited",
    "companies": "checklist_companies_added",
    "courses": "checklist_courses_added",
    "invoices": "checklist_invoice_template_set",
}


def _org_industry(org: Organization):
    """Resolve the org's canonical Industry, defaulting legacy rows to gym."""
    try:
        return get_industry(org.industry or "gym")
    except KeyError:
        return get_industry("gym")


def org_industry_detail(org: Organization) -> dict:
    """Registry metadata for the org's industry (drives client nav/labels)."""
    return public_industry_detail(_org_industry(org).key)


def build_checklist(org: Organization) -> SetupChecklist:
    saas_active = org.saas_status in {SaasStatus.ACTIVE, SaasStatus.TRIALING}
    ind = _org_industry(org)

    steps: list[dict] = []
    prerequisite_codes = [c for c in ind.checklist if c != "done"]
    for code in ind.checklist:
        if code == "done":
            done = saas_active and all(getattr(org, _CHECKLIST_FLAGS[c]) for c in prerequisite_codes)
            steps.append({"code": code, "label": CHECKLIST_LABELS["done"], "done": done})
        else:
            steps.append({"code": code, "label": CHECKLIST_LABELS[code], "done": getattr(org, _CHECKLIST_FLAGS[code])})

    return SetupChecklist(
        saas_active=saas_active,
        stripe_connected=org.checklist_stripe_connected,
        plan_published=org.checklist_plan_published,
        enrollment_configured=org.checklist_enrollment_configured,
        staff_invited=org.checklist_staff_invited,
        office_configured=org.checklist_office_configured,
        # Member signup is blocked until a plan is published (Section 6 constraint).
        member_signup_unblocked=org.checklist_plan_published and saas_active,
        steps=steps,
    )


async def start_connect_onboarding(session: AsyncSession, org: Organization, owner_email: str):
    link = await connect_stripe.create_account_link(email=owner_email)
    org.stripe_connect_account_id = link.account_id
    org.stripe_connect_status = ConnectStatus.PENDING
    session.add(org)
    await record_audit(session, action="org.connect_start", organization_id=org.id,
                       entity_type="organization", entity_id=org.id)
    return link


async def mark_connect_active(session: AsyncSession, org: Organization) -> None:
    """Called by webhook (account.updated) or dev shortcut."""

    org.stripe_connect_status = ConnectStatus.ACTIVE
    org.checklist_stripe_connected = True
    session.add(org)
    await record_audit(session, action="org.connect_active", organization_id=org.id,
                       entity_type="organization", entity_id=org.id)


async def rotate_org_code(session: AsyncSession, org: Organization, *, actor_id: str) -> str:
    """Generate a fresh org code and revoke member sessions (Section 7.5).

    A leaked/abused org code is rotated by the owner. The old code stops working
    immediately; existing member sessions (which were established against the old
    code) are revoked so they must re-authenticate with the new code. Owner/staff
    sessions are left intact so the admin isn't locked out mid-action.
    """

    old_code = org.org_code
    org.org_code = await _unique_org_code(session, org.name, industry=org.industry)
    org.signup_frozen = False  # a fresh code clears any abuse freeze
    session.add(org)

    # Revoke sessions for plain members of this org (Section 5.9 + 7.5).
    member_user_ids = (
        await session.execute(
            select(OrganizationMember.user_id).where(
                OrganizationMember.organization_id == org.id,
                OrganizationMember.role == Role.MEMBER,
            )
        )
    ).scalars()
    revoked = 0
    for uid in member_user_ids:
        sessions = (
            await session.execute(
                select(AuthSession).where(
                    AuthSession.user_id == uid,
                    AuthSession.organization_id == org.id,
                    AuthSession.revoked == False,  # noqa: E712
                )
            )
        ).scalars()
        for s in sessions:
            s.revoked = True
            s.revoked_at = now_utc()
            session.add(s)
            revoked += 1

    await record_audit(session, action="org.code_rotated", organization_id=org.id, actor_user_id=actor_id,
                       entity_type="organization", entity_id=org.id,
                       old_values={"org_code": old_code}, new_values={"org_code": org.org_code},
                       metadata={"sessions_revoked": revoked})
    return org.org_code


async def update_enrollment_mode(session: AsyncSession, org: Organization, mode) -> None:
    org.enrollment_mode = mode
    org.checklist_enrollment_configured = True
    session.add(org)


async def update_org_name(session: AsyncSession, org: Organization, name: str, *, actor_id: str) -> None:
    old_name = org.name
    org.name = name
    session.add(org)
    await record_audit(session, action="org.renamed", organization_id=org.id, actor_user_id=actor_id,
                       entity_type="organization", entity_id=org.id,
                       old_values={"name": old_name}, new_values={"name": name})


async def update_gym_status(session: AsyncSession, org: Organization, gym_status) -> None:
    org.gym_status = gym_status
    session.add(org)
    # Real-time sync: owner toggles status on web -> reflects on mobile (Section 16).
    await events.gym_status_changed(org.id, gym_status=gym_status.value)


# ------------------------------------------------------------------ invoice template
def invoice_settings(org: Organization) -> dict:
    """The org's B2B invoice template (office vertical)."""
    return {
        "legal_name": org.invoice_legal_name,
        "address": org.invoice_address,
        "tax_id": org.invoice_tax_id,
        "payment_terms_days": org.invoice_payment_terms_days,
    }


async def update_invoice_settings(session: AsyncSession, org: Organization, data, *, actor_id: str) -> dict:
    """Persist the B2B invoice template. Any field set completes the 'invoices'
    setup-checklist step (once the office has real company + offer data)."""
    changes = data.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=422, detail="Nothing to update.")
    old = invoice_settings(org)
    # Schema field names (legal_name/address/...) differ from the Organization
    # column names (invoice_legal_name/invoice_address/...). Map explicitly so a
    # PUT actually persists instead of raising on an unmapped attribute.
    _FIELD_TO_COLUMN = {
        "legal_name": "invoice_legal_name",
        "address": "invoice_address",
        "tax_id": "invoice_tax_id",
        "payment_terms_days": "invoice_payment_terms_days",
    }
    for field, value in changes.items():
        setattr(org, _FIELD_TO_COLUMN.get(field, field), value)
    org.checklist_invoice_template_set = True
    session.add(org)
    await record_audit(session, action="org.invoice_settings_updated", organization_id=org.id,
                       actor_user_id=actor_id, entity_type="organization", entity_id=org.id,
                       old_values=old, new_values=changes)
    return invoice_settings(org)
