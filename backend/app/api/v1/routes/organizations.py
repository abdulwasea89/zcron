"""Organization API routes (Sections 3, 4, 7, 16)."""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.api.deps import get_client_ip, get_current_user, get_org, get_session, get_tenant, require_capability
from app.core.constants import MemberStatus, Role, SaasStatus, TIER_MEMBER_CAP, TIER_PRICE_USD
from app.core.security import now_utc
from app.core.config import settings
from app.models.user import User
from app.models.membership import OrganizationMember
from app.core.permissions import Capability
from app.core.tenancy import TenantContext
from app.models.organization import Organization
from app.schemas.common import Message
from app.schemas.organizations import (
    ConnectOnboardingOut,
    CheckoutSessionOut,
    CheckoutConfirmIn,
    CreateOrganizationRequest,
    EnrollmentModeUpdate,
    GymStatusUpdate,
    InvoiceSettings,
    OrgCodeRotateOut,
    OrgNameUpdate,
    OrganizationOut,
    OwnerOnboardingRequest,
    RegisterGymRequest,
    RegisterGymResponse,
    SetupChecklist,
)
from app.services import organizations_service as orgs
from app.integrations.stripe_client import platform_stripe

router = APIRouter()
logger = logging.getLogger(__name__)


def _stripe_setup_error(exc: Exception, action: str) -> str:
    """Give owners a safe next step while keeping Stripe internals off the API."""
    error_type = type(exc).__name__
    if "Authentication" in error_type:
        return "Stripe rejected the platform API key. Check that STRIPE_SECRET_KEY is a valid test secret key, then restart the backend."
    if "Connection" in error_type or "Network" in error_type:
        return "The backend could not reach Stripe. Check the server's internet connection and try again."
    if "Permission" in error_type:
        return "The Stripe account does not have permission to create billing customers. Check the platform account settings."
    if "RateLimit" in error_type:
        return "Stripe is rate limiting requests. Wait a moment and try again."
    if "Idempotency" in error_type:
        return "Stripe rejected a reused request key. Retry once; onboarding now uses request-specific keys."
    if "InvalidRequest" in error_type:
        return f"Stripe rejected the {action} request. Check the backend Stripe diagnostic for the invalid field."
    # Include only a simple mapping key for KeyError. This is useful for local
    # setup failures while avoiding exception text, request bodies, or secrets.
    if isinstance(exc, KeyError) and exc.args:
        missing_key = exc.args[0]
        if isinstance(missing_key, str) and re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", missing_key):
            return f"Stripe could not {action} (server error: missing `{missing_key}`). Check the backend Stripe diagnostic."
    return f"Stripe could not {action} (server error: {error_type}). Check the backend Stripe diagnostic and try again."


@router.post("/onboarding/checkout", response_model=CheckoutSessionOut)
async def onboarding_checkout(
    data: OwnerOnboardingRequest,
    ctx: TenantContext = Depends(get_tenant),
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_org),
    session: AsyncSession = Depends(get_session),
):
    if ctx.role != Role.OWNER or ctx.user_id != user.id:
        raise HTTPException(status_code=403, detail="Only the workspace owner can complete setup.")
    if org.onboarding_complete:
        raise HTTPException(status_code=409, detail="Workspace setup is already complete.")
    if data.tier.value == "enterprise":
        raise HTTPException(status_code=422, detail="Contact sales to set up Enterprise billing.")
    if not user.email_verified:
        raise HTTPException(status_code=403, detail="Verify your email before continuing.")
    if not settings.stripe_live:
        raise HTTPException(
            status_code=503,
            detail="Stripe test mode is not configured. Set the platform STRIPE_SECRET_KEY before continuing.",
        )
    if not platform_stripe.ready:
        raise HTTPException(
            status_code=503,
            detail="Stripe SDK is unavailable on the server. Install the backend Stripe dependency and restart the API.",
        )
    await session.execute(select(Organization).where(Organization.id == org.id).with_for_update())
    await session.refresh(org)
    if org.onboarding_complete:
        raise HTTPException(status_code=409, detail="Workspace setup is already complete.")

    org.name = data.details.name.strip()
    org.country = data.details.country
    org.timezone = data.details.timezone
    org.default_currency = data.details.default_currency
    org.address = data.details.address
    org.logo_url = data.details.logo_url
    org.accent_color = data.details.accent_color
    org.working_hours = data.details.working_hours
    org.industry = data.details.industry
    org.saas_tier = data.tier
    org.member_cap = TIER_MEMBER_CAP[data.tier]
    customer_fingerprint = hashlib.sha256(
        f"{user.email.strip().lower()}\0{data.full_name.strip()}".encode("utf-8")
    ).hexdigest()[:24]
    try:
        customer_id = org.stripe_customer_id or await platform_stripe.create_customer(
            user.email, data.full_name,
            idempotency_key=f"saas-customer-{org.id}-{customer_fingerprint}",
        )
    except Exception as exc:
        logger.error(
            "Stripe onboarding customer creation failed (type=%s code=%s param=%s request_id=%s message=%s)",
            type(exc).__name__, getattr(exc, "code", None), getattr(exc, "param", None),
            getattr(exc, "request_id", None), getattr(exc, "user_message", None),
        )
        raise HTTPException(
            status_code=503,
            detail=_stripe_setup_error(exc, "create the billing customer"),
        ) from exc
    org.stripe_customer_id = customer_id
    for field in ("full_name", "phone", "cnic", "occupation", "education", "address", "city",
                  "date_of_birth", "gender", "emergency_contact"):
        value = getattr(data, field)
        if value is not None:
            setattr(user, field, value)
    member = (await session.execute(select(OrganizationMember).where(
        OrganizationMember.organization_id == org.id, OrganizationMember.user_id == user.id
    ))).scalar_one_or_none()
    if member:
        member.phone = data.phone
        member.profile_complete = True
        session.add(member)

    price = TIER_PRICE_USD[data.tier]
    if price is None:
        raise HTTPException(status_code=422, detail="This plan requires a custom contract.")
    checkout_fingerprint = hashlib.sha256(
        f"{customer_id}\0{data.tier.value}\0{int(price * 100)}\0usd\0{settings.frontend_url}".encode("utf-8")
    ).hexdigest()[:20]
    checkout = None
    checkout_phase = "retrieve existing checkout"
    try:
        if org.stripe_onboarding_session_id:
            prior = await platform_stripe.retrieve_checkout_session(org.stripe_onboarding_session_id)
            if (prior and prior.status == "open" and prior.metadata
                    and prior.metadata.get("organization_id") == org.id
                    and prior.metadata.get("tier") == data.tier.value):
                checkout = prior
            elif prior and prior.status == "open":
                checkout_phase = "expire prior checkout"
                await platform_stripe.expire_checkout_session(prior.id)
        if checkout is None:
            checkout_phase = "create checkout session"
            org.stripe_onboarding_attempt += 1
            checkout = await platform_stripe.create_saas_checkout(
                customer_id=customer_id, org_id=org.id, tier=data.tier.value,
                amount_cents=int(price * 100), currency="usd",
                idempotency_key=(
                    f"saas-onboarding-{org.id}-{checkout_fingerprint}-"
                    f"{org.stripe_onboarding_attempt}"
                ),
            )
    except Exception as exc:
        logger.exception(
            "Stripe onboarding checkout failed during %s (type=%s code=%s param=%s request_id=%s message=%s)",
            checkout_phase,
            type(exc).__name__, getattr(exc, "code", None), getattr(exc, "param", None),
            getattr(exc, "request_id", None), getattr(exc, "user_message", None),
        )
        error_action = {
            "retrieve existing checkout": "retrieve the existing checkout",
            "expire prior checkout": "expire the previous checkout",
            "create checkout session": "create the checkout session",
        }.get(checkout_phase, "create checkout")
        raise HTTPException(
            status_code=503,
            detail=_stripe_setup_error(exc, error_action),
        ) from exc
    if not checkout.url:
        raise HTTPException(status_code=502, detail="Stripe did not return a checkout URL.")
    org.stripe_onboarding_session_id = checkout.id
    session.add_all([org, user])
    return CheckoutSessionOut(checkout_url=checkout.url, session_id=checkout.id)


@router.post("/onboarding/confirm", response_model=OrganizationOut)
async def onboarding_confirm(
    data: CheckoutConfirmIn,
    ctx: TenantContext = Depends(get_tenant),
    org: Organization = Depends(get_org),
    session: AsyncSession = Depends(get_session),
):
    session_id = data.session_id
    if not session_id or session_id != org.stripe_onboarding_session_id:
        raise HTTPException(status_code=400, detail="Checkout session does not match this workspace.")
    checkout = await platform_stripe.retrieve_checkout_session(session_id)
    expected_amount = TIER_PRICE_USD[org.saas_tier]
    if (checkout is None or checkout.status != "complete" or checkout.mode != "subscription"
            or checkout.payment_status not in {"paid", "no_payment_required"}
            or not checkout.metadata or checkout.metadata.get("organization_id") != org.id
            or checkout.metadata.get("tier") != org.saas_tier.value
            or expected_amount is None or checkout.amount_total is None
            or not 0 <= checkout.amount_total <= expected_amount * 100
            or checkout.currency != "usd"
            or not checkout.subscription_id or not checkout.customer_id
            or checkout.customer_id != org.stripe_customer_id
            or checkout.subscription_status != "active"):
        raise HTTPException(status_code=402, detail="Stripe has not confirmed the subscription payment.")
    org.stripe_customer_id = checkout.customer_id
    org.stripe_subscription_id = checkout.subscription_id
    org.saas_status = SaasStatus.ACTIVE
    org.saas_state_changed_at = now_utc()
    org.saas_current_period_end = checkout.current_period_end or now_utc() + timedelta(days=30)
    org.onboarding_complete = True
    member = (await session.execute(select(OrganizationMember).where(
        OrganizationMember.organization_id == org.id, OrganizationMember.user_id == ctx.user_id
    ))).scalar_one_or_none()
    if member:
        member.member_status = MemberStatus.ACTIVE
        member.profile_complete = True
        session.add(member)
    session.add(org)
    await session.flush()
    return _to_out(org)


def _to_out(org: Organization) -> OrganizationOut:
    return OrganizationOut(
        id=org.id,
        name=org.name,
        org_code=org.org_code,
        saas_tier=org.saas_tier.value,
        saas_status=org.saas_status.value,
        enrollment_mode=org.enrollment_mode.value,
        gym_status=org.gym_status.value,
        member_cap=org.member_cap,
        stripe_connect_status=org.stripe_connect_status.value,
        accent_color=org.accent_color,
        logo_url=org.logo_url,
        industry=org.industry,
        default_currency=org.default_currency or "USD",
        country=org.country or "US",
        timezone=org.timezone or "UTC",
        created_at=org.created_at,
        onboarding_complete=org.onboarding_complete,
    )


@router.post("/register", response_model=RegisterGymResponse)
async def register_gym(
    data: RegisterGymRequest, request: Request, session: AsyncSession = Depends(get_session)
):
    """Step 2-4 — complete owner registration & provision the org."""

    org, access, refresh = await orgs.register_gym(session, data, ip=get_client_ip(request))
    return RegisterGymResponse(organization=_to_out(org), access_token=access, refresh_token=refresh)


@router.post("/create", response_model=RegisterGymResponse)
async def create_organization(
    data: CreateOrganizationRequest,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Existing authenticated user creates another gym."""

    org, access, refresh = await orgs.create_organization_for_user(
        session, user, data, ip=get_client_ip(request)
    )
    return RegisterGymResponse(organization=_to_out(org), access_token=access, refresh_token=refresh)


@router.get("/me", response_model=OrganizationOut)
async def get_my_org(org: Organization = Depends(get_org)):
    return _to_out(org)


@router.get("/me/industry")
async def get_my_org_industry(org: Organization = Depends(get_org)):
    """Registry metadata for the current org's industry.

    Drives nav/module/label rendering on web + mobile after login. Never leaks
    another industry's data — public metadata only, keyed by the org's industry.
    """

    return orgs.org_industry_detail(org)


@router.get("/me/checklist", response_model=SetupChecklist)
async def get_checklist(org: Organization = Depends(get_org)):
    return orgs.build_checklist(org)


@router.post("/me/connect", response_model=ConnectOnboardingOut)
async def connect_stripe(
    request: Request,
    ctx: TenantContext = Depends(require_capability(Capability.MANAGE_SETTINGS)),
    org: Organization = Depends(get_org),
    session: AsyncSession = Depends(get_session),
):
    user = await session.get(User, ctx.user_id)
    link = await orgs.start_connect_onboarding(session, org, user.email)
    return ConnectOnboardingOut(account_id=link.account_id, onboarding_url=link.onboarding_url)


@router.post("/me/connect/complete", response_model=Message)
async def connect_complete(
    ctx: TenantContext = Depends(require_capability(Capability.MANAGE_SETTINGS)),
    org: Organization = Depends(get_org),
    session: AsyncSession = Depends(get_session),
):
    """Dev shortcut to mark Connect active (production: Stripe webhook)."""

    await orgs.mark_connect_active(session, org)
    return Message(message="Stripe Connect active.")


@router.patch("/me/enrollment", response_model=Message)
async def set_enrollment(
    data: EnrollmentModeUpdate,
    ctx: TenantContext = Depends(require_capability(Capability.MANAGE_SETTINGS)),
    org: Organization = Depends(get_org),
    session: AsyncSession = Depends(get_session),
):
    await orgs.update_enrollment_mode(session, org, data.enrollment_mode)
    return Message(message="Enrollment mode updated.")


@router.patch("/me/name", response_model=Message)
async def set_org_name(
    data: OrgNameUpdate,
    ctx: TenantContext = Depends(require_capability(Capability.MANAGE_SETTINGS)),
    org: Organization = Depends(get_org),
    session: AsyncSession = Depends(get_session),
):
    """Rename the gym (owner/manager, Section 4.4)."""

    await orgs.update_org_name(session, org, data.name, actor_id=ctx.user_id)
    return Message(message="Gym name updated.")


@router.patch("/me/gym-status", response_model=Message)
async def set_gym_status(
    data: GymStatusUpdate,
    ctx: TenantContext = Depends(require_capability(Capability.TOGGLE_GYM_STATUS)),
    org: Organization = Depends(get_org),
    session: AsyncSession = Depends(get_session),
):
    await orgs.update_gym_status(session, org, data.gym_status)
    return Message(message="Gym status updated.")


@router.post("/me/rotate-code", response_model=OrgCodeRotateOut)
async def rotate_org_code(
    ctx: TenantContext = Depends(require_capability(Capability.MANAGE_SETTINGS)),
    org: Organization = Depends(get_org),
    session: AsyncSession = Depends(get_session),
):
    """Rotate the org code (web-only, owner). Revokes member sessions (Section 7.5)."""

    new_code = await orgs.rotate_org_code(session, org, actor_id=ctx.user_id)
    return OrgCodeRotateOut(org_code=new_code)


@router.get("/me/invoice-settings", response_model=InvoiceSettings)
async def get_invoice_settings(org: Organization = Depends(get_org)):
    """The org's B2B invoice template (office vertical; blank for gym/academy)."""

    return InvoiceSettings(**orgs.invoice_settings(org))


@router.put("/me/invoice-settings", response_model=InvoiceSettings)
async def set_invoice_settings(
    data: InvoiceSettings,
    ctx: TenantContext = Depends(require_capability(Capability.MANAGE_SETTINGS)),
    org: Organization = Depends(get_org),
    session: AsyncSession = Depends(get_session),
):
    """Persist the invoice template. Owner-only; flips the 'invoices' checklist step."""

    return InvoiceSettings(**await orgs.update_invoice_settings(session, org, data, actor_id=ctx.user_id))
