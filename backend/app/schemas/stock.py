"""Items and stock balances."""
from datetime import date, datetime

from pydantic import BaseModel, Field

from .common import DecryptionStatusResponse


class ProductCreate(BaseModel):
    category: str
    name: str = Field(min_length=1, max_length=160)
    unit: str = Field(min_length=1, max_length=80)
    reorder_point: float | None = Field(default=None, ge=0)
    is_active: bool = True


class ProductUpdate(BaseModel):
    category: str | None = None
    name: str | None = Field(default=None, min_length=1, max_length=160)
    unit: str | None = Field(default=None, min_length=1, max_length=80)
    reorder_point: float | None = Field(default=None, ge=0)
    is_active: bool | None = None


class ProductResponse(DecryptionStatusResponse):
    id: int
    category: str
    name: str
    unit: str
    reorder_point: float | None
    on_hand: float
    is_low: bool | None
    is_negative: bool
    is_active: bool
    is_masked: bool
    created_at: datetime
    updated_at: datetime


class ProductListResponse(BaseModel):
    items: list[ProductResponse]
    total: int


class StockBalanceResponse(DecryptionStatusResponse):
    product_id: int
    product_name: str
    unit: str
    quantity: float
    negative: bool
    as_of: date
    is_masked: bool


class StockBalanceListResponse(BaseModel):
    items: list[StockBalanceResponse]
    total: int


class ProductMovementResponse(DecryptionStatusResponse):
    id: int
    product_id: int
    quantity_delta: float
    movement_type: str
    source_type: str | None
    source_id: int | None
    source_label: str | None = None
    occurred_at: datetime
    note: str | None
    voided: bool
    created_at: datetime
    updated_at: datetime
    is_masked: bool


class StockMovementListResponse(BaseModel):
    items: list[ProductMovementResponse]
    total: int


class ProductAdjustmentCreate(BaseModel):
    counted_quantity: float = Field(ge=0)
    unit: str | None = Field(default=None, min_length=1, max_length=80)
    note: str | None = Field(default=None, max_length=500)
    occurred_at: datetime | None = None
