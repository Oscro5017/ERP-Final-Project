"""Shelf life, fresh lots and waste."""
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ShelfLifeUpdate(BaseModel):
    shelf_life_days: int = Field(ge=0, le=3650)
    warn_days: int = Field(default=1, ge=0, le=3650)


class ShelfLifeResponse(ShelfLifeUpdate):
    model_config = ConfigDict(from_attributes=True)
    product_id: int


class FreshLotResponse(BaseModel):
    lot_key: str
    product_id: int
    product_name: str
    unit: str
    cycle_id: int | None
    received_on: date
    expires_on: date
    days_left: int
    received_quantity: float
    remaining_quantity: float
    wasted_quantity: float
    expiry_overridden: bool
    status: Literal["fresh", "expiring", "expired", "empty"]


class FreshProductResponse(BaseModel):
    product_id: int
    product_name: str
    unit: str
    shelf_life_days: int
    warn_days: int
    uncovered_quantity: float


class FreshnessOverviewResponse(BaseModel):
    items: list[FreshLotResponse]
    products: list[FreshProductResponse]
    expired: int
    expiring: int
    is_masked: bool


class LotExpiryUpdate(BaseModel):
    expires_on: date
    reason: str = Field(min_length=1, max_length=500, pattern=r"\S")


class StockWasteCreate(BaseModel):
    product_id: int = Field(gt=0)
    lot_key: str = Field(min_length=1, max_length=40)
    quantity: Decimal = Field(gt=0, le=1_000_000)
    reason: Literal["expired", "spoiled", "damaged", "pest", "other"]
    note: str | None = Field(default=None, max_length=1000)


class StockWasteResponse(BaseModel):
    id: int
    product_id: int
    product_name: str
    lot_key: str
    quantity: float
    unit: str
    reason: str
    note: str | None
    voided: bool
    created_at: datetime
    is_masked: bool
    decrypt_failed: bool


class StockWasteListResponse(BaseModel):
    items: list[StockWasteResponse]
    total: int
