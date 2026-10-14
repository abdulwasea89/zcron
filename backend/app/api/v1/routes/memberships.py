"""Member signup & membership API routes (Sections 8, 9).

The signup sequence is intentionally multi-step (mirrors the mobile flow):
  start -> request-email -> verify-email -> set-password -> plans -> pay -> profile.
Payment requires an Idempotency-Key header (Security Rule #2).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_client_ip, get_session, get_tenant, require_writable_org
from app.core.constants import Role
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
)
from app.services import memberships_service as members
from app.services import members_service as member_admin
from app.services.memberships_service import _org_by_code
from app.services.pricing_service import quote_member_payment
from app.schemas.promotions import PriceQuoteOut
from app.models.plan import MembershipPlan
from sqlmodel import select
from app.models.membership import OrganizationMember
from app.schemas.members import FreezeRequestCreate, FreezeRequestOut

router = APIRouter()


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
            price=p.price, joining_fee=p.joining_fee, currency=p.currency, billing_type=p.billing_type.value,
            featured=p.featured,
            audience=p.audience, family_capacity=p.family_capacity,
            cycle_length=p.cycle_length, cycle_unit=p.cycle_unit,
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
