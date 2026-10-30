"""Retail catalog and stock adjustments."""
from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.api.deps import get_session, require_capability, require_writable_org
from app.core.permissions import Capability
from app.core.tenancy import TenantContext
from app.models.retail import RetailProduct
from app.schemas.retail import ProductCreate, ProductOut, StockAdjustment
from app.services import idempotency_service
from app.services.audit_service import record_audit
from app.services.retail_inventory_service import adjust_stock

router = APIRouter()


@router.get("/products", response_model=list[ProductOut])
async def products(
    ctx: TenantContext = Depends(require_capability(Capability.LOG_CASH_PAYMENT)),
    session: AsyncSession = Depends(get_session),
):
    return (await session.execute(select(RetailProduct).where(
        RetailProduct.organization_id == ctx.org_id,
    ).order_by(RetailProduct.name).limit(1000))).scalars().all()


@router.post("/products", response_model=ProductOut, status_code=201,
             dependencies=[Depends(require_writable_org)])
async def create_product(
    data: ProductCreate,
    ctx: TenantContext = Depends(require_capability(Capability.MANAGE_EXPENSES)),
    session: AsyncSession = Depends(get_session),
    key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    claim = await idempotency_service.claim(session, key=key or "", endpoint="retail.product.create",
        body=data.model_dump(mode="json"), organization_id=ctx.org_id, user_id=ctx.user_id)
    if not claim.claimed:
        return ProductOut.model_validate_json(claim.cached_response or "{}")
    existing = (await session.execute(select(RetailProduct.id).where(
        RetailProduct.organization_id == ctx.org_id, RetailProduct.sku == data.sku,
    ))).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="SKU already exists.")
    product = RetailProduct(organization_id=ctx.org_id, **data.model_dump())
    session.add(product)
    await session.flush()
    await record_audit(session, action="retail.product_created", organization_id=ctx.org_id,
        actor_user_id=ctx.user_id, entity_type="retail_product", entity_id=product.id)
    response = ProductOut.model_validate(product)
    await idempotency_service.complete(session, claim.record, code=201, body=response.model_dump_json())
    return response


@router.post("/products/{product_id}/adjust", response_model=ProductOut,
             dependencies=[Depends(require_writable_org)])
async def stock_adjustment(
    product_id: str, data: StockAdjustment,
    ctx: TenantContext = Depends(require_capability(Capability.MANAGE_EXPENSES)),
    session: AsyncSession = Depends(get_session),
    key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    claim = await idempotency_service.claim(session, key=key or "", endpoint=f"retail.adjust:{product_id}",
        body=data.model_dump(mode="json"), organization_id=ctx.org_id, user_id=ctx.user_id)
    if not claim.claimed:
        return ProductOut.model_validate_json(claim.cached_response or "{}")
    product = await adjust_stock(session, org_id=ctx.org_id, product_id=product_id,
        actor_id=ctx.user_id, delta=data.delta, reason=data.reason)
    response = ProductOut.model_validate(product)
    await idempotency_service.complete(session, claim.record, code=200, body=response.model_dump_json())
    return response
