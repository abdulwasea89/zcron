"""Member signup & membership lifecycle service (Sections 8, 9).

Implements the open-enrollment signup sequence with all gates from the plan:
  * Org-code validation + enrollment-mode check (Section 8.2, 7.1).
  * Layered rate limits: per-IP, per-email, per-org-code (Section 7.2); the
    org-code is auto-frozen when its daily cap is exceeded.
  * CAPTCHA verification (stubbed; Section 7.3).
  * Email verification before payment (Security Rule #6).
  * Idempotent payment via the gym's Stripe Connect account (Section 13, 8.6).
  * Status transitions: pending_payment -> active (or pending_approval).

Approved- and invite-only variants are handled by branching on enrollment mode.
"""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.config import settings
from app.core.constants import (
    ConnectStatus,
    EnrollmentMode,
    MemberStatus,
    PaymentKind,
    PaymentMethod,
    PaymentStatus,
    Role,
    SaasStatus,
    SubscriptionStatus,
    VerificationPurpose,
)
from app.core.rate_limit import rate_limiter
from app.core.security import hash_password, now_utc
from app.core.industry import MoneyMode, get_industry
from app.integrations.email import send_email_safe as send_email
from app.integrations.push import send_push
from app.integrations.stripe_connect import connect_stripe
from app.models.membership import OrganizationMember
from app.models.organization import Organization
from app.models.payment import Payment
from app.models.plan import MembershipPlan
from app.models.signup_attempt import SignupAttempt
from app.models.subscription import Subscription
from app.models.user import User
from app.realtime import events
from app.schemas.auth import LoginResponse
from app.services import auth_service, idempotency_service
from app.services import verification_service as verif
from app.services.audit_service import record_audit
from app.services.pricing_service import quote_member_payment
from app.schemas.promotions import PriceQuoteOut


# ----------------------------------------------------------------- helpers
def _is_b2b_office(org: Organization) -> bool:
    """True when the org is an office vertical (money settles by B2B invoice).

    Office onboarding is invite-only — there is no public join-with-code + pay,
    so every self-serve signup entry point must refuse office orgs."""
    try:
        return get_industry(org.industry or "gym").money == MoneyMode.B2B_INVOICE
    except (KeyError, ValueError):
        return False


def _reject_office_self_signup(org: Organization) -> None:
    if _is_b2b_office(org):
        raise HTTPException(
            status_code=403,
            detail="This office only accepts invited seat-holders. "
                   "Ask your office manager for an invitation.",
        )


async def _org_by_code(session: AsyncSession, org_code: str) -> Organization:
    org = (
        await session.execute(
            select(Organization).where(Organization.org_code == org_code.upper())
        )
    ).scalar_one_or_none()
    if org is None:
        raise HTTPException(status_code=404, detail="Invalid org code.")
    return org


def _verify_captcha(token: str | None) -> None:
    """Stub CAPTCHA check (Section 7.3). In production: verify with hCaptcha /
    Turnstile. Here any non-empty token passes; absence is allowed in dev."""

    # Intentionally permissive in dev/stub mode.
    return None


async def _member_for(session: AsyncSession, org_id: str, user_id: str) -> OrganizationMember | None:
    return (
        await session.execute(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == org_id,
                OrganizationMember.user_id == user_id,
            )
        )
    ).scalar_one_or_none()


async def _active_member_count(session: AsyncSession, org_id: str) -> int:
    """Count members that occupy a SaaS-tier seat (Section 3.1 member cap).

    Mirrors the billing service's definition: active, grace, and frozen members
    all consume a seat; pending/expired/cancelled/banned do not.
    """

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


async def _enforce_signup_rate_limits(
    session: AsyncSession, *, org: Organization, email: str, ip: str | None
) -> None:
    """Layered limits (Section 7.2). Org-code cap auto-freezes the code."""

    if org.signup_frozen:
        raise HTTPException(status_code=429, detail="Signups are temporarily frozen for this gym.")

    ip_key = f"signup:ip:{ip or 'unknown'}"
    ok_ip, _ = await rate_limiter.hit(ip_key, settings.signup_max_per_ip_per_hour, 3600)
    if not ok_ip:
        raise HTTPException(status_code=429, detail="Too many signup attempts. Try again later.")

    email_key = f"signup:email:{email.lower()}"
    ok_email, _ = await rate_limiter.hit(email_key, settings.signup_max_per_email_per_day, 86400)
    if not ok_email:
        raise HTTPException(status_code=429, detail="Too many signup attempts for this email today.")

    code_key = f"signup:org:{org.id}"
    ok_org, _ = await rate_limiter.hit(code_key, settings.signup_max_per_org_code_per_day, 86400)
    if not ok_org:
        org.signup_frozen = True
        session.add(org)
        await record_audit(session, action="org.signup_auto_frozen", organization_id=org.id,
                           entity_type="organization", entity_id=org.id)
        raise HTTPException(status_code=429, detail="This gym has reached its daily signup limit.")


# ------------------------------------------------------------- step 1: code
async def start_signup(
    session: AsyncSession, *, org_code: str, captcha_token: str | None, ip: str | None,
    referral_code: str | None = None,
) -> Organization:
    org = await _org_by_code(session, org_code)
    _verify_captcha(captcha_token)
    _reject_office_self_signup(org)
    if referral_code:
        from app.services.referrals_service import validate_code

        await validate_code(session, org_id=org.id, code=referral_code)

    if org.enrollment_mode == EnrollmentMode.INVITE_ONLY:
        raise HTTPException(status_code=403, detail="This gym is invite-only.")
    if not org.checklist_plan_published:
        raise HTTPException(status_code=409, detail="This gym is not accepting signups yet.")
    if org.saas_status in {SaasStatus.SUSPENDED, SaasStatus.READ_ONLY, SaasStatus.CANCELLED}:
        raise HTTPException(status_code=403, detail="This gym is not accepting signups.")

    session.add(SignupAttempt(organization_id=org.id, org_code=org.org_code, ip_address=ip,
                              status="started"))
    return org


# ---------------------------------------------------- step 3: email + verify
async def request_email_verification(
    session: AsyncSession, *, org_code: str, email: str, captcha_token: str | None, ip: str | None
) -> None:
    org = await _org_by_code(session, org_code)
    _verify_captcha(captcha_token)
    _reject_office_self_signup(org)
    await _enforce_signup_rate_limits(session, org=org, email=email, ip=ip)

    # If email already a member of THIS org -> redirect to login (Section 8.3).
    existing_user = (
        await session.execute(select(User).where(User.email == email.lower()))
    ).scalar_one_or_none()
    if existing_user is not None:
        member = await _member_for(session, org.id, existing_user.id)
        if member is not None:
            raise HTTPException(status_code=409, detail="This email is already a member. Please log in.")

    code = await verif.issue_code(
        session, email=email, purpose=VerificationPurpose.EMAIL_VERIFY, organization_id=org.id
    )
    await send_email(email, "Verify your email", f"Your verification code is {code}")


async def verify_signup_email(
    session: AsyncSession, *, org_code: str, email: str, code: str
) -> None:
    org = await _org_by_code(session, org_code)
    try:
        await verif.verify_and_consume(
            session, email=email, secret=code,
            purpose=VerificationPurpose.EMAIL_VERIFY, organization_id=org.id,
        )
    except verif.VerificationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ------------------------------------------------------- step 4: password
async def set_password(
    session: AsyncSession, *, org_code: str, email: str, password: str,
    referral_code: str | None = None,
) -> OrganizationMember:
    """Create (or reuse) the user and a pending_payment / pending_approval member."""

    org = await _org_by_code(session, org_code)
    await auth_service.validate_password_or_raise(password)
    referred_by = None
    if referral_code:
        from app.services.referrals_service import validate_code

        referred_by = await validate_code(session, org_id=org.id, code=referral_code)

    # The email must have a consumed verification for this org.
    user = (
        await session.execute(select(User).where(User.email == email.lower()))
    ).scalar_one_or_none()
    if user is None:
        user = User(
            email=email.lower(),
            hashed_password=hash_password(password),
            email_verified=True,
        )
        session.add(user)
        await session.flush()
    else:
        # Existing cross-org user joining a new gym (Section 14 / 17.5).
        if not user.email_verified:
            user.email_verified = True
            session.add(user)

    if await _member_for(session, org.id, user.id) is not None:
        raise HTTPException(status_code=409, detail="Already a member of this gym.")

    initial_status = (
        MemberStatus.PENDING_APPROVAL
        if org.enrollment_mode == EnrollmentMode.APPROVED
        else MemberStatus.PENDING_PAYMENT
    )
    member = OrganizationMember(
        organization_id=org.id,
        user_id=user.id,
        role=Role.MEMBER,
        member_status=initial_status,
    )
    session.add(member)
    try:
        await session.flush()
    except IntegrityError as exc:
        # Concurrent signup/invite created the membership first. Roll back this
        # request's pending work and report the conflict like the guard would.
        await session.rollback()
        raise HTTPException(status_code=409, detail="Already a member of this gym.") from exc
    if referred_by is not None:
        from app.services.referrals_service import attach_referral

        await attach_referral(session, org_id=org.id, member_id=member.id, referral_code=referred_by)
    await record_audit(session, action="member.signup_account_created", organization_id=org.id,
                       actor_user_id=user.id, entity_type="member", entity_id=member.id)
    if initial_status == MemberStatus.PENDING_APPROVAL:
        # Approved-enrollment gym: alert the owners there's a signup to decide
        # on (Section 8.3). Best-effort fan-out.
        from app.core.constants import NotificationKind
        from app.services.notifications_service import notify_org_owners

        await notify_org_owners(
            session, org_id=org.id, category=NotificationKind.APPROVAL,
            title="New signup awaiting approval",
            body=f"{user.full_name or email} applied to join your gym and is waiting for approval.",
            data={"member_id": member.id},
        )
    return member


async def redeem_invite(
    session: AsyncSession, *, org_code: str, email: str, code: str, password: str
) -> OrganizationMember:
    """Invited member claims their invite (Section 8.4).

    Consumes the single-use MEMBER_INVITE token, verifies the email, sets the
    password, and moves the member from pending_activation to pending_payment so
    they can pick a plan and pay. This is the counterpart to
    ``members_service.invite_member`` / ``resend_invite`` — without it, invite
    codes are issued but never redeemable."""

    org = await _org_by_code(session, org_code)
    await auth_service.validate_password_or_raise(password)

    try:
        await verif.verify_and_consume(
            session, email=email, secret=code,
            purpose=VerificationPurpose.MEMBER_INVITE, organization_id=org.id,
        )
    except verif.VerificationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    user = (
        await session.execute(select(User).where(User.email == email.lower()))
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="Invited account not found.")
    user.hashed_password = hash_password(password)
    user.email_verified = True
    session.add(user)

    member = await _member_for(session, org.id, user.id)
    if member is None:
        raise HTTPException(status_code=404, detail="Invite is not linked to this gym.")
    # Only a not-yet-claimed invite advances. An already-active member redeeming
    # again is a no-op guard.
    if member.member_status == MemberStatus.PENDING_ACTIVATION:
        if _is_b2b_office(org):
            # Office seat-holders are invited with no payment step: redeeming the
            # invite activates the seat immediately (B2B invoicing to their
            # company — the individual never pays).
            member.member_status = MemberStatus.ACTIVE
            if member.joined_at is None:
                member.joined_at = now_utc()
        else:
            member.member_status = MemberStatus.PENDING_PAYMENT
        session.add(member)
    await record_audit(session, action="member.invite_redeemed", organization_id=org.id,
                       actor_user_id=user.id, entity_type="member", entity_id=member.id)
    return member


# ------------------------------------------------------- step 5: list plans
async def public_plans(session: AsyncSession, *, org: Organization) -> list[MembershipPlan]:
    from app.services.plans_service import list_public_plans

    return await list_public_plans(session, org_id=org.id)


# --------------------------------------------------------- step 6: pay
async def _activate_membership(
    session: AsyncSession, *, org: Organization, member: OrganizationMember, plan: MembershipPlan,
    payment: Payment,
) -> Subscription:
    """Create the subscription (price snapshot) and flip member to active."""

    from app.services.plan_entitlements import subscription_terms

    period_end, classes_remaining = subscription_terms(plan)

    sub = Subscription(
        organization_id=org.id,
        member_id=member.id,
        plan_id=plan.id,
        status=SubscriptionStatus.ACTIVE,
        price_snapshot=plan.price,  # legacy pricing preserved (Section 6.7)
        currency=plan.currency,
        current_period_end=period_end,
        classes_remaining=classes_remaining,
        credits_allowance=classes_remaining,
    )
    session.add(sub)
    await session.flush()

    member.member_status = MemberStatus.ACTIVE
    member.family_owner_member_id = None  # a new purchase replaces family coverage
    if member.joined_at is None:
        member.joined_at = now_utc()
    session.add(member)

    from app.services.family_service import sync_family_status

    await sync_family_status(session, org.id, member.id, MemberStatus.ACTIVE)

    # Start the 90-day onboarding journey (#32). Idempotent: a renewal returns
    # the member's existing journey rather than restarting it.
    from app.services import onboarding_service

    await onboarding_service.start_journey(session, org_id=org.id, member_id=member.id)

    # A lapsed member coming back resolves any open win-back (#36).
    from app.services import winback_service

    await winback_service.mark_recovered(
        session, org_id=org.id, member_id=member.id, amount=payment.amount
    )

    payment.subscription_id = sub.id
    session.add(payment)
    return sub


async def pay_and_activate(
    session: AsyncSession,
    *,
    org_code: str,
    email: str,
    plan_id: str,
    idempotency_key: str,
    promo_code: str | None = None,
    ip: str | None = None,
) -> LoginResponse:
    """Step 6 — idempotent member payment -> activation -> logged in.

    Money flows into the gym's Connect account; the platform never touches it
    (Security Rule #3). The same idempotency key is claimed server-side and
    passed to Stripe (Section 13.5).
    """

    org = await _org_by_code(session, org_code)
    user = (
        await session.execute(select(User).where(User.email == email.lower()))
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="Account not found.")
    member = await _member_for(session, org.id, user.id)
    if member is None:
        raise HTTPException(status_code=404, detail="Membership not found.")
    if member.member_status == MemberStatus.PENDING_APPROVAL:
        raise HTTPException(status_code=403, detail="Awaiting admin approval before payment.")

    plan = await session.get(MembershipPlan, plan_id)
    if plan is None or plan.organization_id != org.id:
        raise HTTPException(status_code=404, detail="Plan not found.")

    # Enforce the SaaS-tier member cap (Section 3.1). A member who already holds
    # a seat (renewal / re-activation) does not count against the cap again.
    if org.member_cap is not None and member.member_status not in {
        MemberStatus.ACTIVE, MemberStatus.GRACE, MemberStatus.FROZEN
    }:
        if await _active_member_count(session, org.id) >= org.member_cap:
            raise HTTPException(
                status_code=402,
                detail="This gym has reached its member capacity. Please contact the gym.",
            )

    # Claim idempotency (Section 13.3). Replays return the cached result.
    endpoint = "POST /memberships/pay"
    claim = await idempotency_service.claim(
        session, key=idempotency_key, endpoint=endpoint,
        body={"org_code": org_code, "email": email, "plan_id": plan_id,
              "promo_code": promo_code.strip().upper() if promo_code else None},
        organization_id=org.id, user_id=user.id,
    )
    if not claim.claimed:
        # Already processed: re-issue a session for the (now active) member.
        access, refresh = await auth_service.create_session(
            session, user=user, org_id=org.id, role=Role.MEMBER, ip=ip
        )
        return LoginResponse(
            access_token=access, refresh_token=refresh, organization_id=org.id,
            role=Role.MEMBER.value, member_status=member.member_status.value,
            user=auth_service.login_user_payload(user, org.id, Role.MEMBER, member),
        )

    quote = await quote_member_payment(
        session, org_id=org.id, member_id=member.id, plan=plan, promo_code=promo_code,
    )
    if quote.total > 0 and org.stripe_connect_status != ConnectStatus.ACTIVE:
        await idempotency_service.fail(session, claim.record, code=402,
                                       body='{"detail":"Gym cannot accept payments yet."}')
        raise HTTPException(status_code=402, detail="This gym cannot accept payments yet.")

    amount = quote.total
    result = None
    if amount > 0:
        result = await connect_stripe.charge_member(
            connected_account_id=org.stripe_connect_account_id,
            amount_cents=int(round(amount * 100)),
            currency=plan.currency.lower(),
            idempotency_key=idempotency_key,
            description=f"{org.name} — {plan.name}",
        )

    payment = Payment(
        organization_id=org.id,
        member_id=member.id,
        plan_id=plan.id,
        kind=PaymentKind.MEMBER_FEE,
        method=PaymentMethod.CARD,
        status=PaymentStatus.SUCCEEDED if result is None or result.status == "succeeded" else PaymentStatus.FAILED,
        amount=amount,
        tax_amount=quote.tax_amount,
        plan_price_amount=quote.plan_price,
        joining_fee_amount=quote.joining_fee,
        discount_amount=quote.discount_amount,
        promo_code=quote.promo_code,
        currency=plan.currency,
        stripe_payment_intent_id=result.id if result else None,
        stripe_charge_id=result.charge_id if result else None,
        idempotency_key=idempotency_key,
        paid_at=now_utc() if result is None or result.status == "succeeded" else None,
    )
    session.add(payment)
    await session.flush()

    if result is not None and result.status != "succeeded":
        await idempotency_service.fail(session, claim.record, code=402,
                                       body='{"detail":"Payment failed."}')
        raise HTTPException(status_code=402, detail="Payment failed. Please retry.")

    await _activate_membership(session, org=org, member=member, plan=plan, payment=payment)
    from app.services.referrals_service import qualify_referral_for_member

    await qualify_referral_for_member(session, org_id=org.id, member_id=member.id)
    await record_audit(session, action="member.activated", organization_id=org.id,
                       actor_user_id=user.id, entity_type="member", entity_id=member.id,
                       metadata={"plan_id": plan.id, "amount": amount})
    await events.membership_changed(org.id, member_id=member.id, status=MemberStatus.ACTIVE.value)
    await send_email(email, "Welcome!", f"Your membership at {org.name} is active.")
    await send_push(None, "Membership active", f"Welcome to {org.name}!")

    from app.core.constants import NotificationKind
    from app.services.notifications_service import create_notification

    await create_notification(
        session, org_id=org.id, recipient_user_id=user.id, category=NotificationKind.MEMBERSHIP,
        title=f"Welcome to {org.name}!",
        body=f"Your {plan.name} membership is active. Let's get started.",
        data={"plan_id": plan.id, "amount": amount, "currency": plan.currency},
    )

    access, refresh = await auth_service.create_session(
        session, user=user, org_id=org.id, role=Role.MEMBER, ip=ip
    )
    response = LoginResponse(
        access_token=access, refresh_token=refresh, organization_id=org.id,
        role=Role.MEMBER.value, member_status=MemberStatus.ACTIVE.value,
        user=auth_service.login_user_payload(user, org.id, Role.MEMBER, member),
    )
    await idempotency_service.complete(session, claim.record, code=200,
                                       body=response.model_dump_json())
    return response


# ------------------------------------------------------- step 7: profile
async def complete_profile(
    session: AsyncSession, *, org_id: str, user_id: str, full_name: str,
    photo_url: str | None, phone: str | None, emergency_contact: str | None,
) -> OrganizationMember:
    member = await _member_for(session, org_id, user_id)
    if member is None:
        raise HTTPException(status_code=404, detail="Membership not found.")
    user = await session.get(User, user_id)
    if user and full_name:
        user.full_name = full_name
        session.add(user)
    member.photo_url = photo_url
    member.phone = phone
    member.emergency_contact = emergency_contact
    member.profile_complete = True
    session.add(member)
    return member
