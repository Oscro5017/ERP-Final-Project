"""Farm tasks."""
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from .common import DecryptionStatusResponse


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    due_date: date
    cycle_id: int | None = None
    status: str = Field(default="pending", pattern="^(pending|done)$")
    source: str = Field(default="manual", pattern="^(auto|manual)$")
    labor_cost: Decimal | None = Field(default=None, ge=0)
    worker_count: int | None = Field(default=None, ge=0)
    extra_cost: Decimal | None = Field(default=None, ge=0)


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    due_date: date | None = None
    cycle_id: int | None = None
    status: str | None = Field(default=None, pattern="^(pending|done)$")
    source: str | None = Field(default=None, pattern="^(auto|manual)$")
    labor_cost: Decimal | None = Field(default=None, ge=0)
    worker_count: int | None = Field(default=None, ge=0)
    extra_cost: Decimal | None = Field(default=None, ge=0)


class TaskCycleInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    cycle_code: str
    table_number: int | None = None
    crop_name: str | None = None


class TaskResponse(DecryptionStatusResponse):
    id: int
    cycle_id: int | None = None
    title: str
    due_date: date
    status: str
    source: str
    labor_cost: Decimal | str | None = None
    worker_count: int | None = None
    extra_cost: Decimal | str | None = None
    created_at: datetime
    cycle_info: TaskCycleInfo | None = None
    order_line_id: int | None = None
    planting_ready: bool = False
    is_masked: bool
