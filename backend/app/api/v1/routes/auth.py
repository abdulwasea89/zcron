"""Auth API routes (Sections 4, 5, 9)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_client_ip, get_current_user, get_session, get_tenant, require_role
from app.core.config import settings
from app.core.constants import Role
from app.core.security import safe_decode
from app.core.tenancy import TenantContext
from app.models.membership import OrganizationMember
from app.models.user import User
from sqlmodel import select
from app.schemas.auth import (
    AdminSessionInfo,
    EmailVerifyRequest,
    LoginRequest,
    LoginResponse,
    MagicLinkRequest,
    MagicLinkVerify,
    MemberLoginRequest,
    MfaConfirm,
    MfaDisable,
    MfaEnrollResponse,
    MfaStatus,
    OwnerRegisterStart,
    PasswordResetConfirm,
    PasswordResetRequest,
    ProfileOut,
    ProfileUpdate,
    RecoverCodesRequest,
    RefreshRequest,
    ResendCodeRequest,
    SessionInfo,
    SwitchOrgRequest,
)

from app.services import auth_service, members_service, mfa_service
from app.services.audit_service import record_audit
from app.schemas.members import MemberProfileUpdate
from app.schemas.common import Message

router = APIRouter()


@router.get("/me")
async def get_me(ctx: TenantContext = Depends(get_tenant), session: AsyncSession = Depends(get_session)):
    """Return the current user's identity and role within the active org."""
    member = (
        await session.execute(
            select(OrganizationMember).where(
                OrganizationMember.user_id == ctx.user_id,
                OrganizationMember.organization_id == ctx.org_id,
            )
        )
    ).scalar_one_or_none()
    return {
        "user_id": ctx.user_id,
        "org_id": ctx.org_id,
        "role": ctx.role.value,
        "member_id": member.id if member else None,
        "member_status": member.member_status.value if member else None,
    }


@router.get("/me/profile", response_model=ProfileOut)
async def get_profile(
    ctx: TenantContext = Depends(get_tenant),
    session: AsyncSession = Depends(get_session),
):
    user = await session.get(User, ctx.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    member = (
        await session.execute(select(OrganizationMember).where(
            OrganizationMember.user_id == ctx.user_id,
            OrganizationMember.organization_id == ctx.org_id,
        ))
    ).scalar_one_or_none()
    return _profile_out(user, member)


def _profile_out(user: User, member: OrganizationMember | None) -> ProfileOut:
    return ProfileOut(
        full_name=user.full_name,
        email=user.email,
        phone=member.phone if member and member.phone is not None else user.phone,
        address=user.address,
        city=user.city,
        occupation=user.occupation,
        education=user.education,
        emergency_contact=member.emergency_contact if member and member.emergency_contact is not None else user.emergency_contact,
        date_of_birth=str(user.date_of_birth) if user.date_of_birth else None,
        gender=user.gender.value if user.gender else None,
        photo_url=member.photo_url if member else None,
        goals=member.goals if member else None,
        health_notes=member.health_notes if member else None,
        id_document_type=member.id_document_type if member else None,
        id_document_last4=member.id_document_last4 if member else None,
        summary=members_service.profile_summary(member, None, include_private=True) if member else None,
        daily_brief_email=bool(member and member.role in {Role.OWNER, Role.MANAGER} and member.daily_brief_email),
    )


@router.patch("/me/profile", response_model=ProfileOut)
async def update_profile(
    data: ProfileUpdate,
    ctx: TenantContext = Depends(get_tenant),
    session: AsyncSession = Depends(get_session),
):
    user = await session.get(User, ctx.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    member = (
        await session.execute(select(OrganizationMember).where(
            OrganizationMember.user_id == ctx.user_id,
            OrganizationMember.organization_id == ctx.org_id,
        ))
    ).scalar_one_or_none()
    if "daily_brief_email" in data.model_fields_set:
        if ctx.role not in {Role.OWNER, Role.MANAGER} or member is None:
            raise HTTPException(status_code=403, detail="Daily owner brief preferences require owner or manager access.")
        value = bool(data.daily_brief_email)
        if member.daily_brief_email != value:
            old = member.daily_brief_email
            member.daily_brief_email = value
            session.add(member)
            await record_audit(
                session, action="profile.daily_brief_email_updated",
                organization_id=ctx.org_id, actor_user_id=ctx.user_id,
                entity_type="organization_member", entity_id=member.id,
                old_values={"daily_brief_email": old}, new_values={"daily_brief_email": value},
            )
    for field in ("full_name", "phone", "address", "city", "occupation", "education", "emergency_contact"):
        if field in data.model_fields_set:
            setattr(user, field, getattr(data, field))
    session.add(user)
    member_fields = data.model_fields_set & MemberProfileUpdate.model_fields.keys()
    if member is not None and member_fields:
        profile_data = MemberProfileUpdate.model_validate(
            {field: getattr(data, field) for field in member_fields}
        )
        member = await members_service.update_member_profile(
            session, org_id=ctx.org_id, member_id=member.id,
            data=profile_data, actor_id=ctx.user_id,
        )
    await session.flush()
    return _profile_out(user, member)


@router.get("/my-organizations")
async def get_my_organizations(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """List all organizations the current user belongs to (org switcher)."""
    return await auth_service.list_user_organizations(session, user)


@router.post("/switch-org", response_model=LoginResponse)
async def switch_org(
    data: SwitchOrgRequest,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Switch to a different organization and get new tokens."""
    access, refresh = await auth_service.switch_organization(
        session, user, data.organization_id,
        ip=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return LoginResponse(access_token=access, refresh_token=refresh)


@router.post("/recover-codes", response_model=Message)
async def recover_codes(data: RecoverCodesRequest, session: AsyncSession = Depends(get_session)):
    """C — Email the user a list of all their gyms and org codes."""
    await auth_service.recover_org_codes(session, data.email)
    return Message(message="If the account exists, your gym codes were sent.")


@router.post("/register", response_model=Message, status_code=status.HTTP_201_CREATED)
async def register_owner(data: OwnerRegisterStart, session: AsyncSession = Depends(get_session)):
    """Step 1 — owner account. Sends a 6-digit email verification code."""

    await auth_service.register_owner_start(session, data)
    return Message(message="Verification code sent to your email.")


@router.post("/verify-email", response_model=Message)
async def verify_email(data: EmailVerifyRequest, session: AsyncSession = Depends(get_session)):
    user = await auth_service.verify_email(session, data.email, data.code)
    from app.services.organizations_service import start_owner_onboarding

    org, access, refresh = await start_owner_onboarding(session, user)
    return {"message": "Email verified.", "access_token": access,
            "refresh_token": refresh, "organization_id": org.id}


@router.post("/resend-code", response_model=Message)
async def resend_code(data: ResendCodeRequest, session: AsyncSession = Depends(get_session)):
    await auth_service.resend_email_code(session, data.email)
    return Message(message="If the account exists, a code was sent.")


@router.post("/login", response_model=LoginResponse)
async def login(data: LoginRequest, request: Request, session: AsyncSession = Depends(get_session)):
    return await auth_service.login(
        session,
        email=data.email,
        password=data.password,
        org_code=data.org_code,
        organization_id=data.organization_id,
        remember=data.remember,
        mfa_code=data.mfa_code,
        ip=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )


@router.post("/member-login", response_model=LoginResponse)
async def member_login(
    data: MemberLoginRequest, request: Request, session: AsyncSession = Depends(get_session)
):
    """Returning member login — validates org_code + email + password together."""

    return await auth_service.login(
        session,
        email=data.email,
        password=data.password,
        org_code=data.org_code,
        remember=data.remember,
        mfa_code=data.mfa_code,
        ip=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )


@router.post("/magic-link/request", response_model=Message)
async def magic_link_request(data: MagicLinkRequest, session: AsyncSession = Depends(get_session)):
    """Mobile login Method B (Section 5.4) — email an admin a single-use link."""

    await auth_service.request_magic_link(session, org_code=data.org_code, email=data.email)
    return Message(message="If the email is an admin of that gym, a sign-in link was sent.")


@router.post("/magic-link/verify", response_model=LoginResponse)
async def magic_link_verify(
    data: MagicLinkVerify, request: Request, session: AsyncSession = Depends(get_session)
):
    """Consume the magic-link token and issue an org-scoped session (Section 5.4)."""

    return await auth_service.verify_magic_link(
        session,
        org_code=data.org_code,
        email=data.email,
        token=data.token,
        remember=data.remember,
        mfa_code=data.mfa_code,
        ip=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )


@router.post("/refresh", response_model=LoginResponse)
async def refresh(data: RefreshRequest, session: AsyncSession = Depends(get_session)):
    return await auth_service.refresh_tokens(session, refresh_token=data.refresh_token)


@router.post("/password-reset/request", response_model=Message)
async def password_reset_request(
    data: PasswordResetRequest, session: AsyncSession = Depends(get_session)
):
    await auth_service.request_password_reset(session, data.email)
    return Message(message="If the account exists, a reset link was sent.")


@router.post("/password-reset/confirm", response_model=Message)
async def password_reset_confirm(
    data: PasswordResetConfirm, session: AsyncSession = Depends(get_session)
):
    await auth_service.confirm_password_reset(
        session, email=data.email, token=data.token, new_password=data.new_password
    )
    return Message(message="Password updated.")


@router.get("/sessions", response_model=list[SessionInfo])
async def list_sessions(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    request: Request = None,
):
    sessions = await auth_service.list_sessions(session, user_id=user.id)
    current_session_id = _session_id_from_request(request)
    return [
        SessionInfo(
            id=s.id,
            device_type=s.device_type,
            os=s.os,
            ip_address=s.ip_address,
            last_activity_at=s.last_activity_at.isoformat() + "Z" if s.last_activity_at else None,
            revoked=s.revoked,
            current=(s.id == current_session_id),
        )
        for s in sessions
    ]


@router.delete("/sessions/{session_id}", response_model=Message)
async def revoke_session(
    session_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await auth_service.revoke_session(session, user_id=user.id, session_id=session_id)
    return Message(message="Session revoked.")


# ----------------------------------------------------------- admin sessions
@router.get("/admin/sessions", response_model=list[AdminSessionInfo])
async def admin_list_sessions(
    tenant: TenantContext = Depends(require_role(Role.OWNER, Role.MANAGER)),
    session: AsyncSession = Depends(get_session),
    request: Request = None,
):
    raw = await auth_service.admin_list_sessions(session, org_id=tenant.org_id)
    current_session_id = _session_id_from_request(request)
    return [
        AdminSessionInfo(**s, current=(s["id"] == current_session_id))
        for s in raw
    ]


@router.delete("/admin/sessions/{session_id}", response_model=Message)
async def admin_revoke_session(
    session_id: str,
    tenant: TenantContext = Depends(require_role(Role.OWNER, Role.MANAGER)),
    session: AsyncSession = Depends(get_session),
):
    await auth_service.admin_revoke_session(session, session_id=session_id, org_id=tenant.org_id)
    return Message(message="Session revoked.")


def _session_id_from_request(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        return None
    payload = safe_decode(auth[7:])
    return payload.get("session_id") if payload else None


# --------------------------------------------------------------------- MFA
@router.get("/mfa", response_model=MfaStatus)
async def mfa_status(user: User = Depends(get_current_user)):
    return MfaStatus(mfa_enabled=user.mfa_enabled)


@router.post("/mfa/enroll", response_model=MfaEnrollResponse)
async def mfa_enroll(
    user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)
):
    """Begin TOTP enrollment — returns the secret + otpauth URI for a QR code."""

    result = await mfa_service.begin_enrollment(session, user=user, issuer=settings.app_name)
    return MfaEnrollResponse(**result)


@router.post("/mfa/confirm", response_model=Message)
async def mfa_confirm(
    data: MfaConfirm,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await mfa_service.confirm_enrollment(session, user=user, code=data.code)
    return Message(message="MFA enabled.")


@router.post("/mfa/disable", response_model=Message)
async def mfa_disable(
    data: MfaDisable,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await mfa_service.disable(session, user=user, password=data.password)
    return Message(message="MFA disabled.")
