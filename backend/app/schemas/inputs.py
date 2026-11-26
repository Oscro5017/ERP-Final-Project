"""Fertiliser and chemical applications."""
from datetime import date, datetime

from pydantic import BaseModel, Field

from .common import DecryptionStatusResponse


class InputItemCreate(BaseModel):
    item_name: str = Field(min_length=1, max_length=140)
    quantity: float = Field(default=0.0, gt=0)
    unit: str = Field(default="", max_length=80)
    product_id: int | None = Field(default=None, gt=0)


class InputItemUpdate(BaseModel):
    item_name: str | None = Field(default=None, min_length=1, max_length=140)
    quantity: float | None = Field(default=None, gt=0)
    unit: str | None = Field(default=None, max_length=80)
    product_id: int | None = Field(default=None, gt=0)


class InputApplicationCreate(BaseModel):
    applied_date: date | None = None
    category: str = Field(default="", max_length=80)
    note: str | None = Field(default=None, max_length=500)
    items: list[InputItemCreate] = Field(default_factory=list)


class InputApplicationUpdate(BaseModel):
    applied_date: date | None = None
    category: str | None = Field(default=None, max_length=80)
    note: str | None = Field(default=None, max_length=500)
    items: list[InputItemCreate] | None = None


class InputItemResponse(DecryptionStatusResponse):
    id: int
    item_name: str
    quantity: float | str | None
    unit: str
    product_id: int | None = None
    is_masked: bool


class InputApplicationResponse(DecryptionStatusResponse):
    id: int
    cycle_id: int
    applied_date: date
    category: str
    note: str | None = None
    items: list[InputItemResponse]
    warnings: list[str] = Field(default_factory=list)
    is_masked: bool


class InputCatalogSuggestionResponse(DecryptionStatusResponse):
    id: int
    item_name: str
    last_unit: str | None = None
    last_category: str | None = None
    last_used_at: datetime | None = None
    use_count: int
    product_id: int | None = None


class InputCatalogSuggestionsResponse(DecryptionStatusResponse):
    items: list[InputCatalogSuggestionResponse]
    is_masked: bool
