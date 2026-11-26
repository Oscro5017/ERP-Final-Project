"""Customer orders and planting for them."""
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from .farm import TableResponse


class SalesOrderLineInput(BaseModel):
    product_id: int = Field(gt=0)
    quantity: Decimal = Field(gt=0, le=1_000_000)
    unit: str | None = Field(default=None, max_length=80)
    delivery_date: date
    unit_price: Decimal | None = Field(default=None, ge=0, le=Decimal("99999999.99"))


class SalesOrderLineUpdate(SalesOrderLineInput):
    id: int | None = None


class SalesOrderCreate(BaseModel):
    customer_id: int = Field(gt=0)
    order_date: date | None = None
    safety_days: int = Field(default=0, ge=0, le=60)
    delivery_location: str | None = Field(default=None, max_length=500)
    note: str | None = Field(default=None, max_length=1000)
    auto_planting: bool = True
    lines: list[SalesOrderLineInput] = Field(min_length=1, max_length=100)


class SalesOrderUpdate(BaseModel):
    customer_id: int | None = Field(default=None, gt=0)
    safety_days: int | None = Field(default=None, ge=0, le=60)
    delivery_location: str | None = Field(default=None, max_length=500)
    note: str | None = Field(default=None, max_length=1000)
    auto_planting: bool | None = None
    lines: list[SalesOrderLineUpdate] | None = Field(default=None, min_length=1, max_length=100)


class SalesOrderClose(BaseModel):
    status: Literal["delivered", "cancelled"]


class SalesOrderDeliverLine(BaseModel):
    line_id: int = Field(gt=0)
    quantity: Decimal = Field(gt=0, le=1_000_000)
    unit_price: Decimal | None = Field(default=None, ge=0, le=Decimal("99999999.99"))
    use_order_price: bool = False


class SalesOrderDeliver(BaseModel):
    doc_date: date | None = None
    note: str | None = Field(default=None, max_length=500)
    record_finance: bool = True
    close_when_complete: bool = True
    lines: list[SalesOrderDeliverLine] = Field(min_length=1, max_length=100)


class SalesOrderLineResponse(BaseModel):
    id: int
    product_id: int
    product_name: str
    crop_name: str | None
    quantity: float
    unit: str
    delivery_date: date
    latest_sow_date: date | None
    planting_status: Literal["unmapped", "not_required", "waiting", "late", "ready", "planted", "covered", "manual", "delivered"]
    delivered_quantity: float
    unit_price: Decimal | str | None
    has_price: bool
    planting_ready: bool
    from_stock: float
    from_growing: float
    to_plant: float
    planting_task_id: int | None
    tables_needed: int | None
    cycle_ids: list[int]


class SalesOrderResponse(BaseModel):
    id: int
    order_no: str
    customer_id: int
    customer_name: str
    order_date: date
    safety_days: int
    delivery_location: str | None
    note: str | None
    status: str
    auto_planting: bool
    lines: list[SalesOrderLineResponse]
    is_masked: bool
    decrypt_failed: bool
    created_at: datetime


class SalesOrderDeliverResponse(BaseModel):
    order: SalesOrderResponse
    document_id: int
    doc_no: str
    warnings: list[str]


class SalesOrderListResponse(BaseModel):
    items: list[SalesOrderResponse]
    total: int


class PlantingProposalResponse(BaseModel):
    line_id: int
    order_no: str
    crop_name: str
    quantity: float
    unit: str
    to_plant: float
    delivery_date: date
    nursery_start: date
    expected_ready_date: date
    is_late: bool
    tables_needed: int | None
    free_tables: list[TableResponse]
    suggested_table_ids: list[int]
    can_create: bool


class PlantingCreate(BaseModel):
    table_ids: list[int] = Field(min_length=1, max_length=49)
    nursery_start: date
    create_tasks: bool = True


class PlantingCreateResponse(BaseModel):
    cycle_ids: list[int]
