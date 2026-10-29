"""Audit authenticated reads without copying response data or search terms."""

from starlette.requests import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.audit_service import record_audit

_PRIVATE_AREAS = {
    "members", "staff", "payroll", "payments", "receipts", "finance", "expenses", "audit",
    "privacy", "inbox", "leads", "retention", "win-back", "onboarding", "nps", "campaigns",
    "referrals", "attendance", "memberships", "saas-billing", "cash", "invoices", "companies",
    "front-desk", "analytics", "inactivity-ladder", "celebrations", "challenges",
}


async def record_read_access(session: AsyncSession, request: Request | None) -> None:
    if request is None or request.method != "GET":
        return
    context = getattr(request.state, "tenant", None)
    if context is None:
        return
    path = request.url.path
    if not path.startswith("/api/v1/"):
        return
    area = path.removeprefix("/api/v1/").split("/", 1)[0]
    if area not in _PRIVATE_AREAS and path != "/api/v1/auth/me/profile":
        return
    route = getattr(request.scope.get("route"), "path", path)
    identifiers = {key: value for key, value in request.path_params.items()
                   if key.endswith("_id") and isinstance(value, str)}
    forwarded_for = request.headers.get("x-forwarded-for")
    client_ip = forwarded_for.split(",", 1)[0].strip() if forwarded_for else (
        request.client.host if request.client else "unknown"
    )
    is_export = path.endswith(("/export", ".csv", ".zip"))
    await record_audit(session, action="privacy.data_accessed", organization_id=context.org_id,
                       actor_user_id=context.user_id, entity_type=area,
                       chain_key=f"read:{context.user_id}",
                       ip_address=client_ip, user_agent=request.headers.get("user-agent", "")[:512],
                       metadata={"route": route, "role": context.role.value, "identifiers": identifiers,
                                 "access_type": "export" if is_export else "read"})
