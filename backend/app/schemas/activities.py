"""Activities: farm work, planned or done."""
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from .common import DecryptionStatusResponse

ActivityStatusValue = Literal["pending", "in_progress", "done"]
EditableKind = Literal["fertilize", "spray", "cleanup", "general"]


class ActivityItemInput(BaseModel):
    item_name: str = Field(min_length=1, max_length=140)
    quantity: Decimal = Field(gt=0)
    unit: str = Field(default="", max_length=80)
    product_id: int | None = Field(default=None, gt=0)


class ActivityShareInput(BaseModel):
    crop_cycle_id: int = Field(gt=0)
    share: float = Field(gt=0, le=1)


class ActivityCreate(BaseModel):
    kind: EditableKind = "general"
    title: str | None = Field(default=None, max_length=200)
    # "done" records work already finished; "pending" plans it and turns the reminder on.
    status: ActivityStatusValue = "done"
    planned_date: date | None = None
    done_on: date | None = None
    cycle_ids: list[int] = Field(default_factory=list)
    table_ids: list[int] = Field(default_factory=list)
    shares: list[ActivityShareInput] = Field(default_factory=list)
    items: list[ActivityItemInput] = Field(default_factory=list)
    note: str | None = Field(default=None, max_length=500)
    remind: bool | None = None
    labor_cost: Decimal | None = Field(default=None, ge=0)
    worker_count: int | None = Field(default=None, ge=0)
    extra_cost: Decimal | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def needs_a_date(self):
        if self.planned_date is None and self.done_on is None and self.status != "done":
            raise ValueError("A planned activity needs a planned date")
        return self


class ActivityUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    planned_date: date | None = None
    done_on: date | None = None
    cycle_ids: list[int] | None = None
    table_ids: list[int] | None = None
    shares: list[ActivityShareInput] | None = None
    items: list[ActivityItemInput] | None = None
    note: str | None = Field(default=None, max_length=500)
    remind: bool | None = None
    labor_cost: Decimal | None = Field(default=None, ge=0)
    worker_count: int | None = Field(default=None, ge=0)
    extra_cost: Decimal | None = Field(default=None, ge=0)
    # Why it was changed after the fact; kept with the change notes.
    reason: str | None = Field(default=None, max_length=300)


class ActivityStatusChange(BaseModel):
    status: ActivityStatusValue
    on_date: date | None = None
    reason: str | None = Field(default=None, max_length=300)


class ActivityTargetResponse(BaseModel):
    crop_cycle_id: int | None = None
    table_id: int | None = None
    table_number: int | None = None
    cycle_code: str | None = None
    crop_name: str | None = None
    share: float | None = None
    share_is_manual: bool = False


class ActivityItemResponse(DecryptionStatusResponse):
    id: int
    item_name: str
    quantity: Decimal | str | None
    unit: str
    product_id: int | None = None


class ActivityResponse(DecryptionStatusResponse):
    id: int
    kind: str
    title: str
    status: str
    source: str
    planned_date: date
    started_on: date | None = None
    done_on: date | None = None
    remind: bool
    note: str | None = None
    labor_cost: Decimal | str | None = None
    worker_count: int | None = None
    extra_cost: Decimal | str | None = None
    targets: list[ActivityTargetResponse]
    items: list[ActivityItemResponse]
    order_line_id: int | None = None
    planting_ready: bool = False
    stock_alert_product_id: int | None = None
    warnings: list[str] = Field(default_factory=list)
    is_masked: bool
    created_at: datetime


class ChangeNoteResponse(DecryptionStatusResponse):
    id: int
    field: str
    old_value: str | None = None
    new_value: str | None = None
    reason: str | None = None
    auto_note: str | None = None
    user_id: int | None = None
    created_at: datetime
    is_masked: bool
