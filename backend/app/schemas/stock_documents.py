"""Inbound and outbound stock documents."""
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .common import DecryptionStatusResponse


class StockDocumentLineCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_id: int = Field(gt=0)
    quantity: Decimal = Field(gt=0, le=Decimal("9999999.999"))
    unit: str | None = Field(default=None, min_length=1, max_length=80)
    unit_price: Decimal | None = Field(default=None, ge=0, le=Decimal("99999999.99"))
    line_amount: Decimal | None = Field(default=None, ge=0, le=Decimal("99999999.99"))


class StockDocumentLineResponse(DecryptionStatusResponse):
    id: int
    line_no: int
    product_id: int
    product_name: str
    quantity: float
    unit: str
    unit_price: str | Decimal | None = None
    line_amount: str | Decimal | None = None
    is_masked: bool


class _StockDocumentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    record_finance: bool | None = None
    doc_date: date | None = None
    crop_cycle_id: int | None = Field(default=None, gt=0)
    reference_no: str | None = Field(default=None, max_length=120)
    note: str | None = Field(default=None, max_length=500)
    lines: list[StockDocumentLineCreate] = Field(min_length=1, max_length=100)


class InboundDocumentCreate(_StockDocumentCreate):
    model_config = ConfigDict(extra="forbid")
    supplier_id: int | None = Field(default=None, gt=0)
    doc_type: Literal["inbound"] = "inbound"


class OutboundDocumentCreate(_StockDocumentCreate):
    model_config = ConfigDict(extra="forbid")
    customer_id: int | None = Field(default=None, gt=0)
    purpose: Literal["sale", "other"] | None = None
    doc_type: Literal["outbound"] = "outbound"


class StockDocumentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reference_no: str | None = Field(default=None, max_length=120)
    note: str | None = Field(default=None, max_length=500)


class StockDocumentVoidRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str | None = Field(default=None, max_length=500)


class StockDocumentResponse(DecryptionStatusResponse):
    id: int
    doc_no: str
    doc_type: str
    doc_date: date
    supplier_id: int | None
    supplier_name: str | None
    customer_id: int | None
    customer_name: str | None
    crop_cycle_id: int | None
    crop_cycle_label: str | None = None
    purpose: str | None = None
    order_id: int | None = None
    order_no: str | None = None
    finance_recorded: bool = False
    reference_no: str | None
    note: str | None
    void_reason: str | None
    total_amount: dict[str, Decimal | str | bool] | None = None
    status: str
    voided_at: datetime | None
    lines: list[StockDocumentLineResponse]
    warnings: list[str] = Field(default_factory=list)
    is_masked: bool
    created_at: datetime
    updated_at: datetime


class LastPriceResponse(BaseModel):
    product_id: int
    unit: str
    unit_price: Decimal


class StockDocumentListResponse(BaseModel):
    items: list[StockDocumentResponse]
    total: int
