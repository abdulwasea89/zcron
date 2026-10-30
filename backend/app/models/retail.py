"""Tenant-scoped retail products and stock movement history."""

from __future__ import annotations

from sqlalchemy import CheckConstraint, UniqueConstraint
from sqlmodel import Field

from app.models.base import TimestampModel, UUIDModel


class RetailProduct(UUIDModel, TimestampModel, table=True):
    __tablename__ = "retail_products"
    __table_args__ = (
        UniqueConstraint("organization_id", "sku", name="uq_retail_product_org_sku"),
        CheckConstraint("stock_quantity >= 0", name="ck_retail_stock_nonnegative"),
        CheckConstraint("price_minor >= 0", name="ck_retail_price_nonnegative"),
        CheckConstraint("low_stock_threshold >= 0", name="ck_retail_threshold_nonnegative"),
    )

    organization_id: str = Field(foreign_key="organizations.id", index=True)
    name: str = Field(max_length=160)
    sku: str = Field(max_length=80)
    currency: str = Field(max_length=3)
    price_minor: int
    stock_quantity: int = 0
    low_stock_threshold: int = 0
    active: bool = True


class RetailStockMovement(UUIDModel, TimestampModel, table=True):
    __tablename__ = "retail_stock_movements"
    __table_args__ = (CheckConstraint("quantity_delta != 0", name="ck_retail_movement_nonzero"),)

    organization_id: str = Field(foreign_key="organizations.id", index=True)
    product_id: str = Field(foreign_key="retail_products.id", index=True)
    actor_user_id: str = Field(foreign_key="users.id")
    quantity_delta: int
    reason: str = Field(max_length=240)
