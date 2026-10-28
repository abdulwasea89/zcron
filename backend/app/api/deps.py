"""FastAPI dependencies: DB session, auth, tenant isolation, capabilities.

This module enforces Security Rule #1 (tenant isolation): the JWT is scoped to
one ``organization_id`` and the ``X-Organization-Id`` header must match it.
"""

from __future__ import annotations


from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.constants import MemberStatus, Role, SaasStatus
from app.core.permissions import Capability, role_has
from app.core.security import ACCESS, safe_decode
from app.core.tenancy import ORG_HEADER, TenantContext
from app.db.session import get_session
from app.models.membership import OrganizationMember
from app.models.organization import Organization
from app.models.session import AuthSession
from app.models.user import User

# Re-export so routers can `from app.api.deps import get_session`.
__all__ = [
    "get_session",
    "get_current_user",
    "get_tenant",
    "require_capability",
    "require_role",
    "require_writable_org",
    "get_client_ip",
]


def get_client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _bearer_token(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return authorization.split(" ", 1)[1].strip()


async def get_current_user(
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> User:
    """Resolve the User from a valid access token. Does NOT scope to an org."""

    token = _bearer_token(authorization)
    payload = safe_decode(token)
    if not payload or payload.get("type") != ACCESS:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    user_id = payload.get("sub")
    user = await session.get(User, user_id) if user_id else None
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    session_id = payload.get("session_id")
    if session_id:
        auth_session = await session.get(AuthSession, session_id)
        if auth_session is None or auth_session.revoked:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session revoked")
    return user


async def get_tenant(
    request: Request,
    authorization: str | None = Header(default=None),
    x_organization_id: str | None = Header(default=None, alias=ORG_HEADER),
    session: AsyncSession = Depends(get_session),
) -> TenantContext:
    """Resolve + enforce tenant scope.

    1. Decode access token -> user_id, org_id, role.
    2. Require X-Organization-Id header to match the JWT org (Security Rule #1).
    3. Verify the membership row still exists and is not banned.
    """

    token = _bearer_token(authorization)
    payload = safe_decode(token)
    if not payload or payload.get("type") != ACCESS:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    user_id = payload.get("sub")
    org_id = payload.get("org_id")
    role = payload.get("role")
    if not user_id or not org_id or not role:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token missing scope")
    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    # Header must match JWT org. Missing header is allowed only if it equals JWT.
    if x_organization_id is not None and x_organization_id != org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organization mismatch",
        )

    membership = (
        await session.execute(
            select(OrganizationMember).where(
                OrganizationMember.user_id == user_id,
                OrganizationMember.organization_id == org_id,
            )
        )
    ).scalar_one_or_none()
    if membership is None or membership.banned or membership.member_status == MemberStatus.BANNED:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No access to organization")

    org = await session.get(Organization, org_id)
    if org is not None and not org.onboarding_complete:
        allowed_during_setup = {
            "/api/v1/organizations/me",
            "/api/v1/auth/me/profile",
            "/api/v1/organizations/onboarding/checkout",
            "/api/v1/organizations/onboarding/confirm",
        }
        if request.url.path not in allowed_during_setup:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Complete workspace setup before using this workspace.",
            )

    if org is not None and org.mfa_required and not user.mfa_enabled:
        allowed_for_mfa_setup = {
            "/api/v1/auth/me",
            "/api/v1/auth/me/profile",
            "/api/v1/auth/mfa",
            "/api/v1/organizations/me",
        }
        if request.url.path not in allowed_for_mfa_setup:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Enable multi-factor authentication to access this organization.",
            )

    session_id = payload.get("session_id")
    if session_id:
        auth_session = await session.get(AuthSession, session_id)
        if (auth_session is None or auth_session.revoked or auth_session.user_id != user_id
                or auth_session.organization_id != org_id):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session revoked")

    try:
        Role(role)
        # Role changes must take effect before existing access tokens expire.
        role_enum = Role(membership.role)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid role")

    context = TenantContext(user_id=user_id, org_id=org_id, role=role_enum)
    request.state.tenant = context
    return context


def require_role(*roles: Role):
    """Dependency factory: require the tenant's role to be one of ``roles``."""

    async def _dep(ctx: TenantContext = Depends(get_tenant)) -> TenantContext:
        if ctx.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return ctx

    return _dep


def require_capability(capability: Capability):
    """Dependency factory: require the tenant's role to hold ``capability``.

    Industry-aware: the check runs against the org's industry overrides, so
    office/academy verticals unlock their own capabilities while gym behavior
    stays exactly the base matrix.
    """

    async def _dep(
        ctx: TenantContext = Depends(get_tenant),
        org: Organization = Depends(get_org),
    ) -> TenantContext:
        if not role_has(ctx.role, capability, industry=org.industry):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This action is not permitted for your role.",
            )
        return ctx

    return _dep


async def get_org(
    ctx: TenantContext = Depends(get_tenant),
    session: AsyncSession = Depends(get_session),
) -> Organization:
    org = await session.get(Organization, ctx.org_id)
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    return org


# States in which the org is read-only or fully locked for SaaS-billing reasons
# (Section 3.5): no plan edits, no new signups, no payroll runs.
_NON_WRITABLE_SAAS = {SaasStatus.READ_ONLY, SaasStatus.SUSPENDED, SaasStatus.CANCELLED, SaasStatus.ARCHIVED}


async def require_writable_org(
    org: Organization = Depends(get_org),
) -> Organization:
    """Block admin writes when the org's SaaS subscription is delinquent.

    On failed SaaS payment the org enters read-only at grace-end and is fully
    suspended later (Section 3.5). In those states the platform must reject
    mutating admin operations (plan edits, payroll runs, cash logging, staff
    changes) while still allowing reads.
    """

    if org.saas_status in _NON_WRITABLE_SAAS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your gym's subscription is past due; the account is read-only. "
                   "Update billing to restore write access.",
        )
    return org
