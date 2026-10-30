from fastapi import HTTPException
import pytest
from sqlalchemy import select

from app.models.retail import RetailProduct, RetailStockMovement
from app.services.retail_inventory_service import adjust_stock


@pytest.mark.asyncio
async def test_stock_adjustment_is_tenant_scoped_and_cannot_go_negative(db):
    product = RetailProduct(organization_id="org-a", name="Bottle", sku="B1", currency="USD", price_minor=500, stock_quantity=3)
    db.add(product)
    await db.flush()
    result = await adjust_stock(db, org_id="org-a", product_id=product.id, actor_id="user-a", delta=-2, reason="Sold")
    assert result.stock_quantity == 1
    with pytest.raises(HTTPException) as insufficient:
        await adjust_stock(db, org_id="org-a", product_id=product.id, actor_id="user-a", delta=-2, reason="Sold")
    assert insufficient.value.status_code == 409
    with pytest.raises(HTTPException) as other_org:
        await adjust_stock(db, org_id="org-b", product_id=product.id, actor_id="user-a", delta=1, reason="Restock")
    assert other_org.value.status_code == 404
    await db.flush()
    rows = (await db.execute(select(RetailStockMovement))).scalars().all()
    assert len(rows) == 1 and rows[0].quantity_delta == -2


@pytest.mark.asyncio
async def test_catalog_and_stock_api_replay_and_tenant_isolation(client):
    from tests.integration.test_domains import _provision_gym

    owner, *_ = await _provision_gym(client, owner_email="retail-owner@g.com")
    other, *_ = await _provision_gym(client, owner_email="retail-other@g.com")
    data = {"name": "Bottle", "sku": "B1", "currency": "USD", "price_minor": 500}
    headers = {**owner, "Idempotency-Key": "product-1"}
    created = await client.post("/api/v1/retail/products", headers=headers, json=data)
    assert created.status_code == 201, created.text
    replay = await client.post("/api/v1/retail/products", headers=headers, json=data)
    assert replay.json()["id"] == created.json()["id"]
    product_id = created.json()["id"]
    assert (await client.get("/api/v1/retail/products", headers=other)).json() == []
    adjust = {**owner, "Idempotency-Key": "adjust-1"}
    body = {"delta": 3, "reason": "Delivery"}
    result = await client.post(f"/api/v1/retail/products/{product_id}/adjust", headers=adjust, json=body)
    assert result.status_code == 200, result.text
    replay = await client.post(f"/api/v1/retail/products/{product_id}/adjust", headers=adjust, json=body)
    assert replay.json()["stock_quantity"] == 3
    denied = await client.post(f"/api/v1/retail/products/{product_id}/adjust", headers={**other, "Idempotency-Key": "other"}, json=body)
    assert denied.status_code == 404
