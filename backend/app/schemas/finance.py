"""Finance entries and insights."""
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .common import DecryptionStatusResponse


class FinanceEntryCreate(BaseModel):
    entry_date: date | None = None
    direction: Literal["income", "expense"]
    category: Literal["sale", "purchase", "labor", "utilities", "equipment", "transport", "other"]
    amount: Decimal = Field(gt=0)
    description: str | None = Field(default=None, max_length=500)
    crop_cycle_id: int | None = Field(default=None, gt=0)
    customer_id: int | None = Field(default=None, gt=0)
    supplier_id: int | None = Field(default=None, gt=0)


class FinanceEntryUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entry_date: date | None = None
    category: Literal["sale", "purchase", "labor", "utilities", "equipment", "transport", "other"] | None = None
    amount: Decimal | None = Field(default=None, gt=0)
    description: str | None = Field(default=None, max_length=500)


class FinanceEntryVoidRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class FinanceEntryResponse(DecryptionStatusResponse):
    id: int
    entry_date: date
    direction: Literal["income", "expense"]
    category: str
    amount: Decimal | str
    description: str | None = None
    source_type: str | None = None
    source_id: int | None = None
    crop_cycle_id: int | None = None
    customer_id: int | None = None
    supplier_id: int | None = None
    is_auto: bool
    status: Literal["posted", "void"]
    void_reason: str | None = None
    voided_at: datetime | None = None
    is_masked: bool
    created_at: datetime
    updated_at: datetime


class FinanceEntryListResponse(BaseModel):
    items: list[FinanceEntryResponse]
    total: int


class InsightStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["new", "seen", "dismissed", "done"]


class InsightResponse(DecryptionStatusResponse):
    id: int
    kind: Literal["insight", "recommendation", "alert"]
    source: Literal["rule", "model", "manual"]
    title: str
    body: str
    severity: str
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    crop_cycle_id: int | None = None
    task_id: int | None = None
    status: Literal["new", "seen", "dismissed", "done"]
    is_masked: bool
    created_at: datetime
    updated_at: datetime
