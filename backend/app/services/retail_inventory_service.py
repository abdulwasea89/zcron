"""Atomic stock adjustments; transaction is owned by the request session."""

from fastapi import HTTPException
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.retail import RetailProduct, RetailStockMovement
from app.services.audit_service import record_audit


async def adjust_stock(
    session: AsyncSession, *, org_id: str, product_id: str, actor_id: str,
    delta: int, reason: str,
) -> RetailProduct:
    if delta == 0 or not reason.strip():
        raise HTTPException(status_code=422, detail="A nonzero adjustment and reason are required.")
    result = await session.execute(
        update(RetailProduct)
        .where(
            RetailProduct.organization_id == org_id,
            RetailProduct.id == product_id,
            RetailProduct.stock_quantity + delta >= 0,
        )
        .values(stock_quantity=RetailProduct.stock_quantity + delta)
        .returning(RetailProduct.id)
    )
    if result.scalar_one_or_none() is None:
        exists = (await session.execute(select(RetailProduct.id).where(
            RetailProduct.organization_id == org_id, RetailProduct.id == product_id,
        ))).scalar_one_or_none()
        if exists is None:
            raise HTTPException(status_code=404, detail="Product not found.")
        raise HTTPException(status_code=409, detail="Insufficient stock.")
    session.add(RetailStockMovement(
        organization_id=org_id, product_id=product_id, actor_user_id=actor_id,
        quantity_delta=delta, reason=reason.strip(),
    ))
    await record_audit(
        session, action="retail.stock_adjusted", organization_id=org_id,
        actor_user_id=actor_id, entity_type="retail_product", entity_id=product_id,
        metadata={"quantity_delta": delta, "reason": reason.strip()},
    )
    product = (await session.execute(select(RetailProduct).where(
        RetailProduct.organization_id == org_id, RetailProduct.id == product_id,
    ).execution_options(populate_existing=True))).scalar_one()
    return product
