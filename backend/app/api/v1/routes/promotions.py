"""Owner and manager controls for membership promo codes."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.api.deps import get_session, require_capability, require_writable_org
from app.core.permissions import Capability
from app.core.tenancy import TenantContext
from app.models.plan import MembershipPlan
from app.models.promotion import Promotion
from app.schemas.promotions import PromotionCreate, PromotionOut, PromotionStatusUpdate

router = APIRouter()


@router.get("", response_model=list[PromotionOut])
async def list_promotions(
    ctx: TenantContext = Depends(require_capability(Capability.VIEW_PLANS)),
    session: AsyncSession = Depends(get_session),
):
    return list((await session.execute(select(Promotion).where(
        Promotion.organization_id == ctx.org_id,
    ).order_by(Promotion.created_at.desc()))).scalars())


@router.post("", response_model=PromotionOut, status_code=201, dependencies=[Depends(require_writable_org)])
async def create_promotion(
    data: PromotionCreate,
    ctx: TenantContext = Depends(require_capability(Capability.CREATE_EDIT_PLANS)),
    session: AsyncSession = Depends(get_session),
):
    if data.plan_id:
        plan = await session.get(MembershipPlan, data.plan_id)
        if plan is None or plan.organization_id != ctx.org_id:
            raise HTTPException(status_code=404, detail="Plan not found.")
    existing = (await session.execute(select(Promotion.id).where(
        Promotion.organization_id == ctx.org_id, Promotion.code == data.code,
    ))).first()
    if existing:
        raise HTTPException(status_code=409, detail="Promo code already exists.")
    promo = Promotion(organization_id=ctx.org_id, **data.model_dump())
    session.add(promo)
    await session.flush()
    return promo


@router.patch("/{promotion_id}", response_model=PromotionOut, dependencies=[Depends(require_writable_org)])
async def update_promotion_status(
    promotion_id: str, data: PromotionStatusUpdate,
    ctx: TenantContext = Depends(require_capability(Capability.CREATE_EDIT_PLANS)),
    session: AsyncSession = Depends(get_session),
):
    promo = await session.get(Promotion, promotion_id)
    if promo is None or promo.organization_id != ctx.org_id:
        raise HTTPException(status_code=404, detail="Promo code not found.")
    promo.active = data.active
    session.add(promo)
    return promo


@router.delete("/{promotion_id}", status_code=204, dependencies=[Depends(require_writable_org)])
async def delete_promotion(
    promotion_id: str,
    ctx: TenantContext = Depends(require_capability(Capability.CREATE_EDIT_PLANS)),
    session: AsyncSession = Depends(get_session),
) -> None:
    promo = await session.get(Promotion, promotion_id)
    if promo is None or promo.organization_id != ctx.org_id:
        raise HTTPException(status_code=404, detail="Promo code not found.")
    await session.delete(promo)
