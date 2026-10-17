"""Member signup & membership API routes (Sections 8, 9).

The signup sequence is intentionally multi-step (mirrors the mobile flow):
  start -> request-email -> verify-email -> set-password -> plans -> pay -> profile.
Payment requires an Idempotency-Key header (Security Rule #2).
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Header, Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_client_ip, get_session, get_tenant, require_writable_org
from app.core.constants import PlanStatus, Role, SubscriptionStatus
from app.core.tenancy import IDEMPOTENCY_HEADER, TenantContext
from app.models.user import User
from app.schemas.auth import LoginResponse
from app.schemas.common import Message
from app.schemas.memberships import (
    MemberOut,
    ProfileComplete,
    PublicPlanOut,
    SignupEmail,
    SignupPay,
    SignupQuote,
    RedeemInvite,
    SignupSetPassword,
    SignupSetPasswordOut,
    SignupStart,
    SignupStartOut,
    SignupVerify,
    WebSignupPaymentIntent,
    WebSignupPaymentConfirm,
    RecurringSetupConfirm,
    RecurringSetupConsent,
)
from app.services import memberships_service as members
from app.services import members_service as member_admin
from app.services.memberships_service import _org_by_code
from app.services.pricing_service import quote_member_payment
from app.schemas.promotions import PriceQuoteOut
from app.models.plan import MembershipPlan
from sqlmodel import select
from app.models.membership import OrganizationMember
from app.models.subscription import Subscription
from app.models.organization import Organization
from app.schemas.members import FreezeRequestCreate, FreezeRequestOut
from app.schemas.members import (MembershipChangeCreate, MembershipChangeOut,
                                 MembershipChangePaymentConfirm, MembershipChangePaymentOut)
from app.services import membership_changes_service as member_changes
from app.services import member_vault_service as member_vault
from pydantic import BaseModel
import json
from fastapi.responses import JSONResponse
from app.services import idempotency_service as idem
from app.core.config import settings

router = APIRouter()


class MembershipCancelIn(BaseModel):
    timing: Literal["now", "period_end"] = "period_end"


class MembershipResumeIn(BaseModel):
    plan_id: str


@router.get("/me/vault")
async def my_membership_vault(ctx: TenantContext = Depends(get_tenant), session: AsyncSession = Depends(get_session)):
    if ctx.role != Role.MEMBER:
        raise HTTPException(status_code=403, detail="Member access required.")
    member = (await session.execute(select(OrganizationMember).where(
        OrganizationMember.organization_id == ctx.org_id, OrganizationMember.user_id == ctx.user_id,
        OrganizationMember.role == Role.MEMBER,
    ))).scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found.")
    return await member_vault.summary(session, ctx.org_id, member.id)


@router.get("/me/payment-config")
async def my_membership_payment_config(ctx: TenantContext = Depends(get_tenant),
                                      session: AsyncSession = Depends(get_session)):
    if ctx.role != Role.MEMBER:
        raise HTTPException(status_code=403, detail="Member access required.")
    org = await session.get(Organization, ctx.org_id)
    if not org or not org.stripe_connect_account_id or not settings.stripe_publishable_key:
        raise HTTPException(status_code=503, detail="Secure member payments are not configured for this gym.")
    return {"publishable_key": settings.stripe_publishable_key,
            "connected_account_id": org.stripe_connect_account_id}


@router.post("/me/cancel")
async def cancel_my_membership(data: MembershipCancelIn,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    ctx: TenantContext = Depends(get_tenant), session: AsyncSession = Depends(get_session)):
    if ctx.role != Role.MEMBER:
        raise HTTPException(status_code=403, detail="Member access required.")
    member = (await session.execute(select(OrganizationMember).where(
        OrganizationMember.organization_id == ctx.org_id, OrganizationMember.user_id == ctx.user_id,
        OrganizationMember.role == Role.MEMBER,
    ))).scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found.")
    claim = await idem.claim(session, key=idempotency_key, endpoint=f"member/cancel/{ctx.org_id}/{member.id}",
                             body=data.model_dump(mode="json"), organization_id=ctx.org_id, user_id=ctx.user_id)
    if not claim.claimed:
        return JSONResponse(json.loads(claim.cached_response), status_code=claim.cached_code)
    result = await member_vault.cancel(session, org_id=ctx.org_id, member_id=member.id,
                                      timing=data.timing, key=idempotency_key)
    await idem.complete(session, claim.record, code=200, body=json.dumps(result))
    return result


@router.post("/me/resume")
async def resume_my_membership(data: MembershipResumeIn,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    ctx: TenantContext = Depends(get_tenant), session: AsyncSession = Depends(get_session)):
    if ctx.role != Role.MEMBER:
        raise HTTPException(status_code=403, detail="Member access required.")
    member = (await session.execute(select(OrganizationMember).where(
        OrganizationMember.organization_id == ctx.org_id, OrganizationMember.user_id == ctx.user_id,
        OrganizationMember.role == Role.MEMBER,
    ))).scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found.")
    claim = await idem.claim(session, key=idempotency_key, endpoint=f"member/resume/{ctx.org_id}/{member.id}",
                             body=data.model_dump(mode="json"), organization_id=ctx.org_id, user_id=ctx.user_id)
    if not claim.claimed:
        return JSONResponse(json.loads(claim.cached_response), status_code=claim.cached_code)
    result = await member_vault.resume(session, org_id=ctx.org_id, member_id=member.id,
                                      plan_id=data.plan_id, key=idempotency_key)
    await idem.complete(session, claim.record, code=200, body=json.dumps(result))
    return result


@router.get("/me/change-requests", response_model=list[MembershipChangeOut])
async def my_membership_change_requests(
    ctx: TenantContext = Depends(get_tenant), session: AsyncSession = Depends(get_session),
):
    if ctx.role != Role.MEMBER:
        raise HTTPException(status_code=403, detail="Member access required.")
    return await member_changes.list_member_requests(session, org_id=ctx.org_id, user_id=ctx.user_id)


@router.get("/me/change-options")
async def membership_change_options(
    ctx: TenantContext = Depends(get_tenant), session: AsyncSession = Depends(get_session),
):
    if ctx.role != Role.MEMBER:
        raise HTTPException(status_code=403, detail="Member access required.")
    member = (await session.execute(select(OrganizationMember).where(
        OrganizationMember.organization_id == ctx.org_id,
        OrganizationMember.user_id == ctx.user_id,
        OrganizationMember.role == Role.MEMBER,
    ))).scalar_one_or_none()
    if member is None:
        raise HTTPException(status_code=404, detail="Member not found.")
    sub = (await session.execute(select(Subscription).where(
        Subscription.organization_id == ctx.org_id,
        Subscription.member_id == member.id,
        Subscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.GRACE]),
    ).order_by(Subscription.started_at.desc()))).scalars().first()
    plans_query = select(MembershipPlan).where(
        MembershipPlan.organization_id == ctx.org_id,
        MembershipPlan.status == PlanStatus.PUBLISHED,
    )
    if sub is not None:
        plans_query = plans_query.where(MembershipPlan.id != sub.plan_id)
    plans = (await session.execute(plans_query.order_by(MembershipPlan.price, MembershipPlan.name))).scalars().all()
    current = await session.get(MembershipPlan, sub.plan_id) if sub is not None else None
    return {
        "current_plan": {"id": current.id, "name": current.name, "price": sub.price_snapshot,
                         "currency": sub.currency} if current and sub else None,
        "plans": [{"id": p.id, "name": p.name, "price": p.price, "currency": p.currency,
                   "billing_type": p.billing_type.value, "cycle_length": p.cycle_length,
                   "cycle_unit": p.cycle_unit, "included_credits": p.included_credits} for p in plans],
    }


@router.post("/me/change-requests", response_model=MembershipChangeOut, status_code=201,
             dependencies=[Depends(require_writable_org)])
async def request_membership_change(
    data: MembershipChangeCreate,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    ctx: TenantContext = Depends(get_tenant), session: AsyncSession = Depends(get_session),
):
    if ctx.role != Role.MEMBER:
        raise HTTPException(status_code=403, detail="Member access required.")
    claim = await idem.claim(session, key=idempotency_key,
                             endpoint=f"member/change-request/{ctx.org_id}/{ctx.user_id}",
                             body=data.model_dump(mode="json"), organization_id=ctx.org_id, user_id=ctx.user_id)
    if not claim.claimed:
        return JSONResponse(json.loads(claim.cached_response), status_code=claim.cached_code)
    result = await member_changes.create_request(
        session, org_id=ctx.org_id, user_id=ctx.user_id, request_type=data.request_type,
        target_plan_id=data.target_plan_id, reason=data.reason,
    )
    payload = result.model_dump(mode="json")
    await idem.complete(session, claim.record, code=201, body=json.dumps(payload))
    return result


@router.post("/me/change-requests/{request_id}/offer-response", response_model=MembershipChangeOut,
             dependencies=[Depends(require_writable_org)])
async def respond_to_membership_save_offer(
    request_id: str, accept: bool,
    ctx: TenantContext = Depends(get_tenant), session: AsyncSession = Depends(get_session),
):
    if ctx.role != Role.MEMBER:
        raise HTTPException(status_code=403, detail="Member access required.")
    return await member_changes.respond_to_offer(
        session, org_id=ctx.org_id, user_id=ctx.user_id, request_id=request_id, accept=accept,
    )


@router.post("/me/change-requests/{request_id}/payment-intent", response_model=MembershipChangePaymentOut,
             dependencies=[Depends(require_writable_org)])
async def start_membership_change_payment(
    request_id: str, ctx: TenantContext = Depends(get_tenant), session: AsyncSession = Depends(get_session),
):
    if ctx.role != Role.MEMBER:
        raise HTTPException(status_code=403, detail="Member access required.")
    return await member_changes.start_upgrade_payment(
        session, org_id=ctx.org_id, user_id=ctx.user_id, request_id=request_id,
    )


@router.post("/me/change-requests/{request_id}/confirm-payment", response_model=MembershipChangeOut,
             dependencies=[Depends(require_writable_org)])
async def confirm_membership_change_payment(
    request_id: str, data: MembershipChangePaymentConfirm,
    ctx: TenantContext = Depends(get_tenant), session: AsyncSession = Depends(get_session),
):
    if ctx.role != Role.MEMBER:
        raise HTTPException(status_code=403, detail="Member access required.")
    return await member_changes.confirm_upgrade_payment(
        session, org_id=ctx.org_id, user_id=ctx.user_id, request_id=request_id,
        payment_intent_id=data.payment_intent_id,
    )


@router.get("/me/freeze-requests", response_model=list[FreezeRequestOut])
async def my_freeze_requests(
    ctx: TenantContext = Depends(get_tenant),
    session: AsyncSession = Depends(get_session),
):
    if ctx.role != Role.MEMBER:
        raise HTTPException(status_code=403, detail="Member access required.")
    return await member_admin.member_freeze_requests(session, org_id=ctx.org_id, user_id=ctx.user_id)


@router.post("/me/freeze-requests", response_model=FreezeRequestOut, status_code=201,
             dependencies=[Depends(require_writable_org)])
async def request_membership_pause(
    data: FreezeRequestCreate,
    ctx: TenantContext = Depends(get_tenant),
    session: AsyncSession = Depends(get_session),
):
    if ctx.role != Role.MEMBER:
        raise HTTPException(status_code=403, detail="Member access required.")
    return await member_admin.create_freeze_request(session, org_id=ctx.org_id, user_id=ctx.user_id, data=data)


@router.delete("/me/freeze-requests/{request_id}", response_model=FreezeRequestOut,
               dependencies=[Depends(require_writable_org)])
async def withdraw_membership_pause(
    request_id: str,
    ctx: TenantContext = Depends(get_tenant),
    session: AsyncSession = Depends(get_session),
):
    if ctx.role != Role.MEMBER:
        raise HTTPException(status_code=403, detail="Member access required.")
    return await member_admin.cancel_freeze_request(session, org_id=ctx.org_id, user_id=ctx.user_id,
                                                    request_id=request_id)


@router.post("/signup/start", response_model=SignupStartOut)
async def signup_start(
    data: SignupStart, request: Request, session: AsyncSession = Depends(get_session)
):
    org = await members.start_signup(
        session, org_code=data.org_code, captcha_token=data.captcha_token,
        ip=get_client_ip(request), referral_code=data.referral_code,
    )
    return SignupStartOut(
        organization_id=org.id,
        organization_name=org.name,
        enrollment_mode=org.enrollment_mode.value,
        accepting_signups=not org.signup_frozen,
    )


@router.post("/signup/request-email", response_model=Message)
async def signup_request_email(
    data: SignupEmail, request: Request, session: AsyncSession = Depends(get_session)
):
    await members.request_email_verification(
        session, org_code=data.org_code, email=data.email,
        captcha_token=data.captcha_token, ip=get_client_ip(request),
    )
    return Message(message="Verification code sent.")


@router.post("/signup/verify-email", response_model=Message)
async def signup_verify_email(data: SignupVerify, session: AsyncSession = Depends(get_session)):
    await members.verify_signup_email(
        session, org_code=data.org_code, email=data.email, code=data.code
    )
    return Message(message="Email verified.")


@router.post("/signup/set-password", response_model=SignupSetPasswordOut)
async def signup_set_password(
    data: SignupSetPassword, session: AsyncSession = Depends(get_session)
):
    member = await members.set_password(
        session, org_code=data.org_code, email=data.email, password=data.password,
        referral_code=data.referral_code,
    )
    return SignupSetPasswordOut(
        member_id=member.id,
        organization_id=member.organization_id,
        member_status=member.member_status.value,
    )


@router.post("/invite/redeem", response_model=SignupSetPasswordOut)
async def redeem_invite(data: RedeemInvite, session: AsyncSession = Depends(get_session)):
    """Invited member claims their invite code + sets a password (Section 8.4).

    After this they proceed to /signup/plans -> /signup/pay like any member."""

    member = await members.redeem_invite(
        session, org_code=data.org_code, email=data.email, code=data.code, password=data.password
    )
    return SignupSetPasswordOut(
        member_id=member.id,
        organization_id=member.organization_id,
        member_status=member.member_status.value,
    )


@router.get("/signup/plans", response_model=list[PublicPlanOut])
async def signup_plans(org_code: str, session: AsyncSession = Depends(get_session)):
    org = await _org_by_code(session, org_code)
    plans = await members.public_plans(session, org=org)
    return [
        PublicPlanOut(
            id=p.id, name=p.name, public_description=p.public_description,
            price=p.price,
            renewal_total=p.price * (1 + p.tax_rate if p.tax_mode.value == "added" else 1),
            joining_fee=p.joining_fee, currency=p.currency, billing_type=p.billing_type.value,
            featured=p.featured,
            audience=p.audience, family_capacity=p.family_capacity,
            cycle_length=p.cycle_length, cycle_unit=p.cycle_unit, auto_renew=p.auto_renew,
            pack_size=p.pack_size, validity_days=p.validity_days,
            included_credits=p.included_credits,
            off_peak_start=p.off_peak_start, off_peak_end=p.off_peak_end,
        )
        for p in plans
    ]


@router.post("/signup/quote", response_model=PriceQuoteOut)
async def signup_quote(data: SignupQuote, session: AsyncSession = Depends(get_session)):
    org = await _org_by_code(session, data.org_code)
    user = (await session.execute(select(User).where(User.email == data.email.lower()))).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="Membership not found.")
    member = (await session.execute(select(OrganizationMember).where(
        OrganizationMember.organization_id == org.id,
        OrganizationMember.user_id == user.id,
    ))).scalar_one_or_none()
    if member is None:
        raise HTTPException(status_code=404, detail="Membership not found.")
    plan = await session.get(MembershipPlan, data.plan_id)
    if plan is None or plan.organization_id != org.id:
        raise HTTPException(status_code=404, detail="Plan not found.")
    return await quote_member_payment(session, org_id=org.id, member_id=member.id,
                                      plan=plan, promo_code=data.promo_code)


@router.post("/signup/pay", response_model=LoginResponse)
async def signup_pay(
    data: SignupPay,
    request: Request,
    idempotency_key: str = Header(default="", alias=IDEMPOTENCY_HEADER),
    session: AsyncSession = Depends(get_session),
):
    return await members.pay_and_activate(
        session, org_code=data.org_code, email=data.email, plan_id=data.plan_id,
        idempotency_key=idempotency_key, promo_code=data.promo_code, ip=get_client_ip(request),
    )


@router.post("/me/signup/payment-intent")
async def start_web_signup_payment(
    data: WebSignupPaymentIntent,
    ctx: TenantContext = Depends(get_tenant),
    session: AsyncSession = Depends(get_session),
):
    if ctx.role != Role.MEMBER:
        raise HTTPException(status_code=403, detail="Member access required.")
    return await members.create_web_signup_payment(
        session, org_id=ctx.org_id, user_id=ctx.user_id,
        plan_id=data.plan_id, promo_code=data.promo_code, auto_renew=data.auto_renew,
    )


@router.post("/me/signup/confirm-payment")
async def confirm_web_signup_payment(
    data: WebSignupPaymentConfirm,
    ctx: TenantContext = Depends(get_tenant),
    session: AsyncSession = Depends(get_session),
):
    if ctx.role != Role.MEMBER:
        raise HTTPException(status_code=403, detail="Member access required.")
    return await members.confirm_web_signup_payment(
        session, org_id=ctx.org_id, user_id=ctx.user_id,
        payment_intent_id=data.payment_intent_id,
    )


@router.get("/me/recurring-billing")
async def recurring_billing_status(
    ctx: TenantContext = Depends(get_tenant), session: AsyncSession = Depends(get_session),
):
    if ctx.role != Role.MEMBER:
        raise HTTPException(status_code=403, detail="Member access required.")
    return await members.recurring_billing_status(session, org_id=ctx.org_id, user_id=ctx.user_id)


@router.post("/me/recurring-billing/setup-intent")
async def start_recurring_method_setup(
    data: RecurringSetupConsent,
    ctx: TenantContext = Depends(get_tenant), session: AsyncSession = Depends(get_session),
):
    if ctx.role != Role.MEMBER:
        raise HTTPException(status_code=403, detail="Member access required." )
    if not data.consent:
        raise HTTPException(status_code=422, detail="Consent is required to authorize recurring payments.")
    return await members.create_recurring_setup_intent(session, org_id=ctx.org_id, user_id=ctx.user_id)


@router.post("/me/recurring-billing/confirm")
async def confirm_recurring_method_setup(
    data: RecurringSetupConfirm,
    ctx: TenantContext = Depends(get_tenant), session: AsyncSession = Depends(get_session),
):
    if ctx.role != Role.MEMBER:
        raise HTTPException(status_code=403, detail="Member access required.")
    return await members.confirm_recurring_setup(
        session, org_id=ctx.org_id, user_id=ctx.user_id, setup_intent_id=data.setup_intent_id,
    )


@router.post("/me/profile", response_model=MemberOut)
async def complete_profile(
    data: ProfileComplete,
    ctx: TenantContext = Depends(get_tenant),
    session: AsyncSession = Depends(get_session),
):
    member = await members.complete_profile(
        session, org_id=ctx.org_id, user_id=ctx.user_id, full_name=data.full_name,
        photo_url=data.photo_url, phone=data.phone, emergency_contact=data.emergency_contact,
    )
    user = await session.get(User, ctx.user_id)
    return MemberOut(
        member_id=member.id, user_id=ctx.user_id, email=user.email if user else "",
        full_name=user.full_name if user else None, role=member.role.value,
        member_status=member.member_status.value, profile_complete=member.profile_complete,
    )
