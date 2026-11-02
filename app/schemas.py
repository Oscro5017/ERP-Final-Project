from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from .models import CycleStatus, Role


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: Role


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


class CropCycleCreate(BaseModel):
    table_id: int
    batch_id: int
    crop_type_id: int
    nursery_start: date
    transplant_date: date | None = None
    harvest_date: date | None = None
    harvest_quantity_kg: float | None = Field(default=None, ge=0)
    status: CycleStatus = CycleStatus.nursery


class CropCycleUpdate(BaseModel):
    status: CycleStatus | None = None
    nursery_start: date | None = None
    transplant_date: date | None = None
    harvest_date: date | None = None
    harvest_quantity_kg: float | None = Field(default=None, ge=0)


class CropCycleResponse(CropCycleCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    cycle_code: str
    table: TableResponse
    batch: BatchResponse
    crop_type: CropTypeResponse


class CropCycleStatusLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    cycle_id: int
    from_status: str | None = None
    to_status: str
    changed_at: datetime


class CustomerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    contact: str = Field(default="", max_length=160)


class CustomerResponse(BaseModel):
    id: int
    name: str
    contact: str
    is_masked: bool


class InputItemCreate(BaseModel):
    item_name: str = Field(min_length=1, max_length=140)
    quantity: float = Field(default=0.0, gt=0)
    unit: str = Field(default="", max_length=80)


class InputItemUpdate(BaseModel):
    item_name: str | None = Field(default=None, min_length=1, max_length=140)
    quantity: float | None = Field(default=None, gt=0)
    unit: str | None = Field(default=None, max_length=80)


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


class InputItemResponse(BaseModel):
    id: int
    item_name: str
    quantity: float | str
    unit: str
    is_masked: bool


class InputApplicationResponse(BaseModel):
    id: int
    cycle_id: int
    applied_date: date
    category: str
    note: str | None = None
    items: list[InputItemResponse]
    is_masked: bool


class InputCatalogSuggestionResponse(BaseModel):
    id: int
    item_name: str
    last_unit: str | None = None
    last_category: str | None = None
    last_used_at: datetime | None = None
    use_count: int


class InputCatalogSuggestionsResponse(BaseModel):
    items: list[InputCatalogSuggestionResponse]
    is_masked: bool


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    due_date: date
    cycle_id: int | None = None
    status: str = Field(default="pending", pattern="^(pending|done)$")
    source: str = Field(default="manual", pattern="^(auto|manual)$")


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    due_date: date | None = None
    cycle_id: int | None = None
    status: str | None = Field(default=None, pattern="^(pending|done)$")
    source: str | None = Field(default=None, pattern="^(auto|manual)$")


class TaskCycleInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    cycle_code: str
    table_number: int | None = None
    crop_name: str | None = None


class TaskResponse(BaseModel):
    id: int
    cycle_id: int | None = None
    title: str
    due_date: date
    status: str
    source: str
    created_at: datetime
    cycle_info: TaskCycleInfo | None = None
    is_masked: bool


class WeatherForecastDay(BaseModel):
    date: date
    temp_min: float
    temp_max: float
    humidity: float
    rainfall: float
    condition: str
    weather_code: int


class WeatherLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    log_date: date
    temp_min: float
    temp_max: float
    humidity: float
    rainfall: float
    condition: str
    fetched_at: datetime


class WeatherSyncResponse(BaseModel):
    message: str
    log: WeatherLogResponse | None = None


class SensorReadingInput(BaseModel):
    device_id: str = Field(min_length=1, max_length=100)
    sensor_type: str = Field(min_length=1, max_length=40)
    value: float
    unit: str = Field(min_length=1, max_length=20)
    recorded_at: datetime


class SensorReadingsCreate(BaseModel):
    readings: list[SensorReadingInput] = Field(min_length=1, max_length=1000)


class SensorReadingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    device_id: str
    sensor_type: str
    value: float
    unit: str
    recorded_at: datetime
    received_at: datetime


class SensorReadingsAccepted(BaseModel):
    accepted_count: int
    updated_count: int

