"""Validation for the retail catalog and inventory."""
from pydantic import BaseModel, ConfigDict, Field, field_validator


class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    sku: str = Field(min_length=1, max_length=80)
    currency: str = Field(min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")
    price_minor: int = Field(ge=0, le=100000000)
    low_stock_threshold: int = Field(default=0, ge=0, le=1000000)

    @field_validator("name", "sku")
    @classmethod
    def strip_required(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("This field is required.")
        return value


class ProductOut(ProductCreate):
    model_config = ConfigDict(from_attributes=True)
    id: str
    stock_quantity: int
    active: bool


class StockAdjustment(BaseModel):
    delta: int = Field(ge=-1000000, le=1000000)
    reason: str = Field(min_length=1, max_length=240)
