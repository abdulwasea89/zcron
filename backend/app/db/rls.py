"""Transaction-local PostgreSQL row-level security scope."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings


async def set_rls_context(
    session: AsyncSession,
    *,
    organization_id: str | None = None,
    user_id: str | None = None,
    bypass: bool = False,
) -> None:
    # shortcut: public and worker paths trust app validation, use separate DB roles before treating RLS as a hard boundary.
    if settings.is_sqlite:
        return
    await session.execute(
        text(
            "SELECT set_config('app.organization_id', :org, true), "
            "set_config('app.user_id', :user, true), "
            "set_config('app.rls_bypass', :bypass, true)"
        ),
        {
            "org": organization_id or "",
            "user": user_id or "",
            "bypass": "on" if bypass else "off",
        },
    )
