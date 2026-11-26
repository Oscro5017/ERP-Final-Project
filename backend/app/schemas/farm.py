"""Tables, batches, crop types and crop cycles."""
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from ..models import CycleStatus


class TableResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    table_number: int


class BatchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    batch_number: int
    start_date: date
    week_offset: int


class CropTypeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    nursery_days: int
    growth_days: int
    product_id: int | None = None
    warnings: list[str] = Field(default_factory=list)


class CropTypeProductMappingUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_id: int | None = Field(default=None, gt=0)


class _CropCycleFields(BaseModel):
    table_id: int
    batch_id: int
    crop_type_id: int
    nursery_start: date
    transplant_date: date | None = None
    harvest_date: date | None = None
    harvest_quantity_kg: float | None = Field(default=None, ge=0)
    status: CycleStatus = CycleStatus.nursery


class CropCycleCreate(_CropCycleFields):
    create_tasks: bool | None = None
    record_harvest_stock: bool | None = None


class CropCycleUpdate(BaseModel):
    create_tasks: bool | None = None
    record_harvest_stock: bool | None = None
    status: CycleStatus | None = None
    nursery_start: date | None = None
    transplant_date: date | None = None
    harvest_date: date | None = None
    harvest_quantity_kg: float | None = Field(default=None, ge=0)


class CropCycleResponse(_CropCycleFields):
    model_config = ConfigDict(from_attributes=True)
    id: int
    cycle_code: str
    table: TableResponse
    batch: BatchResponse
    crop_type: CropTypeResponse
    warnings: list[str] = Field(default_factory=list)


class CropCycleStatusLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    cycle_id: int
    from_status: str | None = None
    to_status: str
    changed_at: datetime
