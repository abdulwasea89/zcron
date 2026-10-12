"""Promotion management and server-authoritative membership quotes."""

from datetime import datetime, timezone

from pydantic import BaseModel, Field, field_validator, model_validator


class PromotionCreate(BaseModel):
    code: str = Field(min_length=3, max_length=32, pattern=r"^[A-Za-z0-9_-]+$")
    plan_id: str | None = None
    discount_type: str = Field(pattern=r"^(percent|fixed)$")
    discount_value: float = Field(gt=0)
    starts_at: datetime | None = None
    ends_at: datetime | None = None

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.upper()

    @model_validator(mode="after")
    def valid_terms(self):
        if self.starts_at and self.starts_at.tzinfo:
            self.starts_at = self.starts_at.astimezone(timezone.utc).replace(tzinfo=None)
        if self.ends_at and self.ends_at.tzinfo:
            self.ends_at = self.ends_at.astimezone(timezone.utc).replace(tzinfo=None)
        if self.discount_type == "percent" and self.discount_value > 100:
            raise ValueError("Percentage discounts cannot exceed 100%.")
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            raise ValueError("End date must follow start date.")
        return self


class PromotionStatusUpdate(BaseModel):
    active: bool


class PromotionOut(BaseModel):
    id: str
    code: str
    plan_id: str | None
    discount_type: str
    discount_value: float
    active: bool
    starts_at: datetime | None
    ends_at: datetime | None


class PriceQuoteOut(BaseModel):
    plan_price: float
    joining_fee: float
    discount_amount: float
    tax_amount: float
    total: float
    currency: str
    promo_code: str | None
    first_purchase: bool
