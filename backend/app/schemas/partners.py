"""Customers and suppliers."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from .common import DecryptionStatusResponse


class CustomerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    contact: str = Field(default="", max_length=160)
    area: str | None = Field(default=None, max_length=500)


class CustomerUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=160)
    contact: str | None = Field(default=None, max_length=160)
    area: str | None = Field(default=None, max_length=500)


class CustomerResponse(DecryptionStatusResponse):
    id: int
    name: str
    contact: str
    area: str | None = None
    is_masked: bool


class SupplierCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=160)
    contact: str | None = Field(default=None, max_length=240)
    area: str | None = Field(default=None, max_length=500)
    note: str | None = Field(default=None, max_length=500)
    is_active: bool = True


class SupplierUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=160)
    contact: str | None = Field(default=None, max_length=240)
    area: str | None = Field(default=None, max_length=500)
    note: str | None = Field(default=None, max_length=500)
    is_active: bool | None = None


class SupplierResponse(DecryptionStatusResponse):
    id: int
    name: str
    contact: str
    area: str
    note: str
    is_active: bool
    is_masked: bool
    warnings: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class SupplierListResponse(BaseModel):
    items: list[SupplierResponse]
    total: int
