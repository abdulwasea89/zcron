"""Owner-managed, encrypted inbox channel connections."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session, require_capability
from app.core.permissions import Capability
from app.core.tenancy import TenantContext
from app.schemas.inbox_channels import InboxChannelConnectIn
from app.services import inbox_channels_service as channels

router = APIRouter()


@router.get("/channels")
async def list_channels(
    ctx: TenantContext = Depends(require_capability(Capability.MANAGE_SETTINGS)),
    session: AsyncSession = Depends(get_session),
):
    return await channels.list_connections(session, ctx.org_id)


@router.put("/channels/{channel}")
async def connect_channel(
    channel: str,
    data: InboxChannelConnectIn,
    ctx: TenantContext = Depends(require_capability(Capability.MANAGE_SETTINGS)),
    session: AsyncSession = Depends(get_session),
):
    return await channels.connect(session, org_id=ctx.org_id, channel=channel, source=data.credentials)


@router.delete("/channels/{channel}", status_code=204)
async def disconnect_channel(
    channel: str,
    ctx: TenantContext = Depends(require_capability(Capability.MANAGE_SETTINGS)),
    session: AsyncSession = Depends(get_session),
):
    await channels.disconnect(session, org_id=ctx.org_id, channel=channel)
    return Response(status_code=204)
