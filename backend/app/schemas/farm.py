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
    seed_product_id: int | None = None
    warnings: list[str] = Field(default_factory=list)


class CropTypeUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nursery_days: int | None = Field(default=None, ge=0, le=365)
    growth_days: int | None = Field(default=None, ge=0, le=365)
    seed_product_id: int | None = Field(default=None, gt=0)


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
    seed_count: int | None = Field(default=None, ge=0)
    plant_count: int | None = Field(default=None, ge=0)
    expected_transplant_on: date | None = None
    expected_ready_on: date | None = None


class CropCycleCreate(_CropCycleFields):
    create_tasks: bool | None = None
    record_harvest_stock: bool | None = None
    # Take the seeds out of stock when the crop type names its seed item (default yes).
    deduct_seeds: bool = True


class CropCycleUpdate(BaseModel):
    create_tasks: bool | None = None
    record_harvest_stock: bool | None = None
    status: CycleStatus | None = None
    nursery_start: date | None = None
    transplant_date: date | None = None
    harvest_date: date | None = None
    harvest_quantity_kg: float | None = Field(default=None, ge=0)
    seed_count: int | None = Field(default=None, ge=0)
    plant_count: int | None = Field(default=None, ge=0)
    expected_transplant_on: date | None = None
    expected_ready_on: date | None = None
    deduct_seeds: bool | None = None
    # Why the cycle was changed after the fact; kept with the change notes.
    reason: str | None = Field(default=None, max_length=300)


class CropCycleStatusChange(BaseModel):
    """Change the stage from a list in one step, giving only what that stage needs."""
    status: CycleStatus
    on_date: date | None = None
    plant_count: int | None = Field(default=None, ge=0)
    quantity_kg: float | None = Field(default=None, gt=0)
    reason: str | None = Field(default=None, max_length=300)


class HarvestEntryCreate(BaseModel):
    harvested_on: date | None = None
    quantity_kg: float = Field(gt=0)
    final: bool = False
    reason: str | None = Field(default=None, max_length=300)


class HarvestEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    crop_cycle_id: int
    activity_id: int | None = None
    harvested_on: date
    quantity_kg: float
    voided_at: datetime | None = None
    created_at: datetime


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
