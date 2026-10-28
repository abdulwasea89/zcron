"""Authentication & session service (Sections 4.2-4.3, 5, 9).

Responsibilities:
  * Owner registration start + email verification.
  * Login with deliberately vague errors (Security Rule #4).
  * Member login validating org_code + email + password together (Section 9.1).
  * Failed-login lockout (Section 5.7).
  * Session issuance/tracking/revocation (Section 5.9).
  * Password reset (Section 5.8).

Token issuance is org-scoped: an access/refresh token always names ONE
organization_id (Security Rule, Section 9.2).
"""

from __future__ import annotations

import hashlib
from datetime import timedelta

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.config import settings
from app.core.constants import ADMIN_ROLES, MemberStatus, Role, VerificationPurpose
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    hash_token,
    now_utc,
    password_complexity_errors,
    verify_password,
)
from app.core.rate_limit import rate_limiter
from app.integrations.email import send_email, send_email_safe
from app.integrations.hibp import password_is_pwned
from app.models.membership import OrganizationMember
from app.models.organization import Organization
from app.models.session import AuthSession
from app.models.user import User
from app.realtime import events
from app.schemas.auth import (
    LoginResponse,
    OwnerRegisterStart,
)
from app.services import verification_service as verif
from app.services.audit_service import record_audit

_VAGUE = "Invalid credentials."


def login_user_payload(
    user: User, org_id: str, role: Role, member: OrganizationMember | None = None
) -> dict:
    """Build the ``user`` object embedded in LoginResponse (used by mobile)."""
    return {
        "user_id": user.id,
        "email": user.email,
        "role": role.value,
        "org_id": org_id,
        "member_id": member.id if member else None,
        "member_status": member.member_status.value if member and member.member_status else None,
    }


async def _get_user_by_email(session: AsyncSession, email: str) -> User | None:
    return (
        await session.execute(select(User).where(User.email == email.lower()))
    ).scalar_one_or_none()


async def validate_password_or_raise(password: str) -> None:
    errors = password_complexity_errors(password)
    if errors:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=errors)
    if await password_is_pwned(password):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=["This password has appeared in a data breach. Choose another."],
        )


# --------------------------------------------------------------- registration
async def register_owner_start(session: AsyncSession, data: OwnerRegisterStart) -> User:
    """Create an unverified owner User and send a 6-digit code (Section 4.2-4.3)."""

    if data.password != data.confirm_password:
        raise HTTPException(status_code=422, detail=["Passwords do not match."])
    await validate_password_or_raise(data.password)

    existing = await _get_user_by_email(session, data.email)
    if existing is not None:
        # Don't reveal account existence beyond what's necessary.
        raise HTTPException(status_code=409, detail="Email already registered.")

    user = User(
        email=data.email.lower(),
        full_name=data.email.split("@", 1)[0],
        hashed_password=hash_password(data.password),
        email_verified=False,
    )
    session.add(user)
    await session.flush()

    code = await verif.issue_code(
        session, email=user.email, purpose=VerificationPurpose.EMAIL_VERIFY, user_id=user.id
    )
    await send_email(user.email, "Verify your email", f"Your verification code is {code}")
    await record_audit(session, action="owner.register_start", actor_user_id=user.id,
                       entity_type="user", entity_id=user.id)
    return user


async def verify_email(session: AsyncSession, email: str, code: str) -> User:
    try:
        await verif.verify_and_consume(
            session, email=email, secret=code, purpose=VerificationPurpose.EMAIL_VERIFY
        )
    except verif.VerificationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    user = await _get_user_by_email(session, email)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")
    user.email_verified = True
    session.add(user)
    await record_audit(session, action="user.email_verified", actor_user_id=user.id,
                       entity_type="user", entity_id=user.id)
    return user


async def resend_email_code(session: AsyncSession, email: str) -> None:
    user = await _get_user_by_email(session, email)
    if user is None or user.email_verified:
        return  # silent — don't leak account state
    try:
        code = await verif.issue_code(
            session, email=email, purpose=VerificationPurpose.EMAIL_VERIFY, user_id=user.id
        )
    except verif.VerificationError as exc:
        raise HTTPException(status_code=429, detail=str(exc))
    await send_email_safe(email, "Verify your email", f"Your verification code is {code}")


# ----------------------------------------------------------------- lockout
def _is_locked(user: User) -> bool:
    return user.locked_until is not None and user.locked_until > now_utc()


async def _register_failure(session: AsyncSession, user: User) -> None:
    user.failed_login_count += 1
    if user.failed_login_count >= settings.max_login_attempts:
        user.locked_until = now_utc() + timedelta(minutes=settings.login_lockout_minutes)
        user.failed_login_count = 0
        await send_email_safe(user.email, "Account locked",
                              "Your account was locked after too many failed login attempts.")
    session.add(user)


async def _register_success(session: AsyncSession, user: User) -> None:
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now_utc()
    session.add(user)


# ------------------------------------------------------------------- sessions
async def create_session(
    session: AsyncSession,
    *,
    user: User,
    org_id: str,
    role: Role,
    remember: bool = False,
    device_type: str | None = None,
    os: str | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
) -> tuple[str, str]:
    """Issue access+refresh tokens and persist a tracked session."""

    refresh = create_refresh_token(user_id=user.id, org_id=org_id, role=role.value)
    days = settings.remember_device_days if remember else settings.refresh_token_expire_days
    auth_session = AuthSession(
        user_id=user.id,
        organization_id=org_id,
        refresh_token_hash=hash_token(refresh),
        device_type=device_type,
        os=os,
        ip_address=ip,
        user_agent=user_agent,
        last_activity_at=now_utc(),
        expires_at=now_utc() + timedelta(days=days),
        remember_device=remember,
    )
    session.add(auth_session)
    await session.flush()

    access = create_access_token(
        user_id=user.id, org_id=org_id, role=role.value,
        remember=remember, session_id=auth_session.id,
    )

    # Persist last-used org so next login goes here (B — last-used org).
    user.last_org_id = org_id
    session.add(user)

    await events.sessions_changed(org_id)
    return access, refresh


async def _org_memberships(session: AsyncSession, user_id: str) -> list[OrganizationMember]:
    return list(
        (
            await session.execute(
                select(OrganizationMember).where(OrganizationMember.user_id == user_id)
            )
        ).scalars()
    )


async def _resolve_membership(
    session: AsyncSession,
    *,
    user: User,
    org_code: str | None,
    organization_id: str | None,
) -> tuple[Organization, OrganizationMember]:
    """Find the org membership for login. Raises vague 401 on any miss."""

    org: Organization | None = None
    if organization_id:
        org = await session.get(Organization, organization_id)
    elif org_code:
        org = (
            await session.execute(
                select(Organization).where(Organization.org_code == org_code.upper())
            )
        ).scalar_one_or_none()

    if org is None:
        raise HTTPException(status_code=401, detail=_VAGUE)

    membership = (
        await session.execute(
            select(OrganizationMember)
            .where(
                OrganizationMember.user_id == user.id,
                OrganizationMember.organization_id == org.id,
            )
            # One row per (org, user) is enforced by a unique constraint; this
            # deterministic most-recent fallback keeps login from hard-crashing
            # if a legacy duplicate ever slips through (MultipleResultsFound).
            .order_by(OrganizationMember.created_at.desc())
        )
    ).scalars().first()
    if membership is None:
        raise HTTPException(status_code=401, detail=_VAGUE)
    return org, membership


# --------------------------------------------------------------------- login
async def login(
    session: AsyncSession,
    *,
    email: str,
    password: str,
    org_code: str | None = None,
    organization_id: str | None = None,
    remember: bool = False,
    mfa_code: str | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
) -> LoginResponse:
    """Unified login. Vague errors throughout (Security Rule #4)."""

    normalized_email = email.strip().lower()
    email_key = hashlib.sha256(normalized_email.encode()).hexdigest()
    allowed_email, _ = await rate_limiter.hit(
        f"login:email:{email_key}", settings.login_max_per_email,
        settings.failed_login_window_minutes * 60,
    )
    allowed_ip, _ = await rate_limiter.hit(
        f"login:ip:{ip or 'unknown'}", settings.login_max_per_ip,
        settings.failed_login_window_minutes * 60,
    )
    if not allowed_email or not allowed_ip:
        raise HTTPException(status_code=429, detail="Too many login attempts. Try again later.")

    user = await _get_user_by_email(session, normalized_email)
    if user is None:
        raise HTTPException(status_code=401, detail=_VAGUE)
    if _is_locked(user):
        raise HTTPException(status_code=423, detail="Account temporarily locked. Try again later.")
    if not verify_password(password, user.hashed_password):
        await _register_failure(session, user)
        # Persist the counter before raising; the request dependency rolls back
        # transactions when an HTTPException escapes the route.
        await session.commit()
        raise HTTPException(status_code=401, detail=_VAGUE)
    if not user.email_verified:
        raise HTTPException(status_code=403, detail="Email not verified.")

    memberships = await _org_memberships(session, user.id)
    if not memberships:
        raise HTTPException(status_code=401, detail=_VAGUE)

    target: OrganizationMember | None = None
    if organization_id or org_code:
        _, target = await _resolve_membership(
            session, user=user, org_code=org_code, organization_id=organization_id
        )
    elif len(memberships) == 1:
        target = memberships[0]
    else:
        # B — last-used org auto-login (Section: Last-Used Org).
        if user.last_org_id:
            target = next(
                (m for m in memberships if m.organization_id == user.last_org_id),
                None,
            )
        if target is None:
            target = max(memberships, key=lambda m: m.joined_at or now_utc())

    if target.banned or target.member_status == MemberStatus.BANNED:
        raise HTTPException(status_code=403, detail="Access denied.")

    # MFA challenge (Section 5.5): if enabled and no/invalid code, return a
    # tokenless response telling the client to collect a TOTP code and retry.
    if user.mfa_enabled:
        from app.services import mfa_service

        if not mfa_service.check_code(user, mfa_code):
            await _register_success(session, user)  # password was correct
            return LoginResponse(
                access_token="", refresh_token="", requires_mfa=True,
                organization_id=target.organization_id, role=target.role.value,
                user=login_user_payload(user, target.organization_id, target.role, target),
            )

    await _register_success(session, user)
    access, refresh = await create_session(
        session, user=user, org_id=target.organization_id, role=target.role,
        remember=remember, ip=ip, user_agent=user_agent,
    )
    await record_audit(session, action="auth.login", actor_user_id=user.id,
                       organization_id=target.organization_id, ip_address=ip)
    return LoginResponse(
        access_token=access,
        refresh_token=refresh,
        organization_id=target.organization_id,
        role=target.role.value,
        member_status=target.member_status.value,
        # MFA challenge already satisfied here (we issued tokens) -> False.
        requires_mfa=False,
        user=login_user_payload(user, target.organization_id, target.role, target),
    )


# ------------------------------------------------------------------- refresh
async def refresh_tokens(
    session: AsyncSession, *, refresh_token: str
) -> LoginResponse:
    from app.core.security import safe_decode, REFRESH

    payload = safe_decode(refresh_token)
    if not payload or payload.get("type") != REFRESH:
        raise HTTPException(status_code=401, detail="Invalid refresh token.")

    token_hash = hash_token(refresh_token)
    auth_session = (
        await session.execute(
            select(AuthSession).where(AuthSession.refresh_token_hash == token_hash)
        )
    ).scalar_one_or_none()
    if auth_session is None or auth_session.revoked:
        raise HTTPException(status_code=401, detail="Session revoked or invalid.")
    if auth_session.expires_at and auth_session.expires_at < now_utc():
        raise HTTPException(status_code=401, detail="Session expired.")

    user = await session.get(User, payload["sub"])
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Invalid session.")

    role = Role(payload["role"])
    org_id = payload["org_id"]
    access = create_access_token(user_id=user.id, org_id=org_id, role=role.value)
    auth_session.last_activity_at = now_utc()
    session.add(auth_session)
    return LoginResponse(
        access_token=access, refresh_token=refresh_token, organization_id=org_id, role=role.value,
        user=login_user_payload(user, org_id, role),
    )


# --------------------------------------------------------------- magic link
async def request_magic_link(
    session: AsyncSession, *, org_code: str, email: str
) -> None:
    """Mobile login Method B (Section 5.4): email an admin a single-use link.

    Silent on every miss (unknown org, non-member, non-admin, unverified) so the
    endpoint never reveals whether the email is an admin of the org.
    """

    org = (
        await session.execute(
            select(Organization).where(Organization.org_code == org_code.upper())
        )
    ).scalar_one_or_none()
    if org is None:
        return

    user = await _get_user_by_email(session, email)
    if user is None or not user.email_verified:
        return

    membership = (
        await session.execute(
            select(OrganizationMember).where(
                OrganizationMember.user_id == user.id,
                OrganizationMember.organization_id == org.id,
            )
        )
    ).scalar_one_or_none()
    # Magic link is an admin-only convenience (Section 5.4 "an admin of that org").
    if membership is None or membership.role not in ADMIN_ROLES:
        return

    try:
        token = await verif.issue_link_token(
            session, email=user.email, purpose=VerificationPurpose.MAGIC_LINK,
            organization_id=org.id, user_id=user.id,
            expire_minutes=settings.magic_link_expire_minutes,
        )
    except verif.VerificationError:
        return  # rate-limited — stay silent
    await send_email_safe(
        user.email, "Your sign-in link",
        f"Tap to sign in to {org.name}. Single-use, expires in "
        f"{settings.magic_link_expire_minutes} minutes. Token: {token}",
    )


async def verify_magic_link(
    session: AsyncSession,
    *,
    org_code: str,
    email: str,
    token: str,
    remember: bool = False,
    mfa_code: str | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
) -> LoginResponse:
    """Consume a magic-link token and issue an org-scoped session (Section 5.4)."""

    org = (
        await session.execute(
            select(Organization).where(Organization.org_code == org_code.upper())
        )
    ).scalar_one_or_none()
    if org is None:
        raise HTTPException(status_code=401, detail=_VAGUE)

    try:
        await verif.verify_and_consume(
            session, email=email, secret=token,
            purpose=VerificationPurpose.MAGIC_LINK, organization_id=org.id,
        )
    except verif.VerificationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    user = await _get_user_by_email(session, email)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail=_VAGUE)

    _, target = await _resolve_membership(
        session, user=user, org_code=None, organization_id=org.id
    )
    if target.banned or target.member_status == MemberStatus.BANNED:
        raise HTTPException(status_code=403, detail="Access denied.")

    # MFA still applies after a magic link (Section 5.5: triggered after magic link).
    if user.mfa_enabled:
        from app.services import mfa_service

        if not mfa_service.check_code(user, mfa_code):
            return LoginResponse(
                access_token="", refresh_token="", requires_mfa=True,
                organization_id=target.organization_id, role=target.role.value,
                user=login_user_payload(user, target.organization_id, target.role, target),
            )

    await _register_success(session, user)
    access, refresh = await create_session(
        session, user=user, org_id=target.organization_id, role=target.role,
        remember=remember, ip=ip, user_agent=user_agent,
    )
    await record_audit(session, action="auth.magic_link_login", actor_user_id=user.id,
                       organization_id=target.organization_id, ip_address=ip)
    return LoginResponse(
        access_token=access, refresh_token=refresh,
        organization_id=target.organization_id, role=target.role.value,
        member_status=target.member_status.value, requires_mfa=False,
        user=login_user_payload(user, target.organization_id, target.role, target),
    )


# ------------------------------------------------------------ password reset
async def request_password_reset(session: AsyncSession, email: str) -> None:
    user = await _get_user_by_email(session, email)
    if user is None:
        return  # silent
    token = await verif.issue_link_token(
        session, email=email, purpose=VerificationPurpose.PASSWORD_RESET, user_id=user.id,
        expire_minutes=settings.password_reset_expire_minutes,
    )
    await send_email_safe(email, "Reset your password", f"Use this token to reset: {token}")


async def confirm_password_reset(
    session: AsyncSession, *, email: str, token: str, new_password: str
) -> None:
    await validate_password_or_raise(new_password)
    try:
        await verif.verify_and_consume(
            session, email=email, secret=token, purpose=VerificationPurpose.PASSWORD_RESET
        )
    except verif.VerificationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    user = await _get_user_by_email(session, email)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")
    user.hashed_password = hash_password(new_password)
    session.add(user)
    # Revoke all sessions on password change (Section 5.6 sensitive action).
    await revoke_all_sessions(session, user_id=user.id)
    await record_audit(session, action="auth.password_reset", actor_user_id=user.id)


# --------------------------------------------------------- session management
async def list_sessions(session: AsyncSession, *, user_id: str) -> list[AuthSession]:
    return list(
        (
            await session.execute(
                select(AuthSession).where(AuthSession.user_id == user_id)
            )
        ).scalars()
    )


async def revoke_session(session: AsyncSession, *, user_id: str, session_id: str) -> None:
    auth_session = await session.get(AuthSession, session_id)
    if auth_session is None or auth_session.user_id != user_id:
        raise HTTPException(status_code=404, detail="Session not found.")
    auth_session.revoked = True
    auth_session.revoked_at = now_utc()
    session.add(auth_session)
    org_id = auth_session.organization_id
    if org_id:
        await events.sessions_changed(org_id)


async def revoke_all_sessions(session: AsyncSession, *, user_id: str) -> None:
    for s in await list_sessions(session, user_id=user_id):
        s.revoked = True
        s.revoked_at = now_utc()
        session.add(s)


async def admin_list_sessions(
    session: AsyncSession, *, org_id: str,
) -> list[dict]:
    """List all sessions in an org with user info. Owner/manager only."""
    result = await session.execute(
        select(AuthSession, User)
        .join(User, AuthSession.user_id == User.id)
        .where(AuthSession.organization_id == org_id)
        .order_by(AuthSession.last_activity_at.desc().nullslast())
    )
    rows: list[dict] = []
    for auth_s, user in result:
        rows.append({
            "id": auth_s.id,
            "user_id": user.id,
            "user_email": user.email,
            "user_name": user.full_name,
            "device_type": auth_s.device_type,
            "os": auth_s.os,
            "ip_address": auth_s.ip_address,
            "user_agent": auth_s.user_agent,
            "last_activity_at": auth_s.last_activity_at.isoformat() + "Z"
                if auth_s.last_activity_at else None,
            "revoked": auth_s.revoked,
        })
    return rows


async def admin_revoke_session(
    session: AsyncSession, *, session_id: str, org_id: str,
) -> None:
    """Revoke ANY session within the org. Owner/manager only."""
    auth_session = await session.get(AuthSession, session_id)
    if auth_session is None or auth_session.organization_id != org_id:
        raise HTTPException(status_code=404, detail="Session not found.")
    auth_session.revoked = True
    auth_session.revoked_at = now_utc()
    session.add(auth_session)
    await events.sessions_changed(org_id)


# --------------------------------------------------------- org code recovery
async def recover_org_codes(session: AsyncSession, email: str) -> None:
    """C — Email the user a list of all their gyms and org codes (Section: Email Recovery).

    Silent on unknown email to avoid revealing account existence.
    """

    user = await _get_user_by_email(session, email)
    if user is None:
        return

    memberships = await _org_memberships(session, user.id)
    if not memberships:
        return

    lines = []
    for m in memberships:
        o = await session.get(Organization, m.organization_id)
        if o:
            lines.append(f"  {o.name}  →  {o.org_code}")

    if not lines:
        return

    body = (
        "Here are your gyms on Acron:\n\n"
        + "\n".join(lines)
        + "\n\n"
        + "Use any code on the login page to go straight to that gym.\n"
        + "Or just leave the code blank — we'll take you to your last gym."
    )
    await send_email_safe(email, "Your gym codes", body)


# --------------------------------------------------------- multi-org switching
async def list_user_organizations(
    session: AsyncSession, user: User
) -> list[dict]:
    """Return all orgs the user belongs to (for the org switcher)."""

    memberships = await _org_memberships(session, user.id)
    result = []
    for m in memberships:
        o = await session.get(Organization, m.organization_id)
        if o:
            result.append({
                "organization_id": o.id,
                "name": o.name,
                "org_code": o.org_code,
                "role": m.role.value,
                "member_status": m.member_status.value if m.member_status else None,
                # Venue vertical (gym | office | academy) — lets clients theme the
                # org switcher / tab bars without a second round-trip.
                "industry": o.industry,
            })
    return result


async def switch_organization(
    session: AsyncSession,
    user: User,
    target_org_id: str,
    *,
    ip: str | None = None,
    user_agent: str | None = None,
) -> tuple[str, str]:
    """Issue new tokens scoped to a different org the user belongs to."""

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Access denied.")

    membership = (
        await session.execute(
            select(OrganizationMember)
            .where(
                OrganizationMember.user_id == user.id,
                OrganizationMember.organization_id == target_org_id,
            )
            # One row per (org, user) is enforced by a unique constraint; this
            # deterministic most-recent fallback keeps switch from hard-crashing
            # if a legacy duplicate ever slips through (MultipleResultsFound).
            .order_by(OrganizationMember.created_at.desc())
        )
    ).scalars().first()
    if membership is None or membership.banned or membership.member_status == MemberStatus.BANNED:
        raise HTTPException(status_code=403, detail="You don't have access to that organization.")

    user.last_org_id = target_org_id
    session.add(user)

    access, refresh = await create_session(
        session, user=user, org_id=target_org_id, role=membership.role,
        ip=ip, user_agent=user_agent,
    )
    await record_audit(session, action="auth.switch_org", actor_user_id=user.id,
                       organization_id=target_org_id, ip_address=ip)
    return access, refresh
