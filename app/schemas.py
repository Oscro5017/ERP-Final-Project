from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_serializer

from .models import CycleStatus, FINANCE_CATEGORIES, FINANCE_DIRECTIONS, Role


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
    product_id: int | None = None
    warnings: list[str] = Field(default_factory=list)


class CropTypeProductMappingUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_id: int | None = Field(default=None, gt=0)


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
    warnings: list[str] = Field(default_factory=list)


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
    area: str | None = Field(default=None, max_length=500)


class CustomerUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=160)
    contact: str | None = Field(default=None, max_length=160)
    area: str | None = Field(default=None, max_length=500)


class DecryptionStatusResponse(BaseModel):
    decrypt_failed: bool = False

    @model_serializer(mode="wrap")
    def serialize_decryption_status(self, handler):
        data = handler(self)
        if not self.decrypt_failed:
            data.pop("decrypt_failed", None)
        return data


class CustomerResponse(DecryptionStatusResponse):
    id: int
    name: str
    contact: str
    area: str | None = None
    is_masked: bool


class ProductCreate(BaseModel):
    category: str
    name: str = Field(min_length=1, max_length=160)
    unit: str = Field(min_length=1, max_length=80)
    reorder_point: float | None = Field(default=None, ge=0)
    is_active: bool = True


class ProductUpdate(BaseModel):
    category: str | None = None
    name: str | None = Field(default=None, min_length=1, max_length=160)
    unit: str | None = Field(default=None, min_length=1, max_length=80)
    reorder_point: float | None = Field(default=None, ge=0)
    is_active: bool | None = None


class ProductResponse(DecryptionStatusResponse):
    id: int
    category: str
    name: str
    unit: str
    reorder_point: float | None
    on_hand: float
    is_low: bool | None
    is_negative: bool
    is_active: bool
    is_masked: bool
    created_at: datetime
    updated_at: datetime


class ProductListResponse(BaseModel):
    items: list[ProductResponse]
    total: int


class StockBalanceResponse(DecryptionStatusResponse):
    product_id: int
    product_name: str
    unit: str
    quantity: float
    negative: bool
    as_of: date
    is_masked: bool


class StockBalanceListResponse(BaseModel):
    items: list[StockBalanceResponse]
    total: int


class ProductMovementResponse(DecryptionStatusResponse):
    id: int
    product_id: int
    quantity_delta: float
    movement_type: str
    source_type: str | None
    source_id: int | None
    occurred_at: datetime
    note: str | None
    voided: bool
    created_at: datetime
    updated_at: datetime
    is_masked: bool


class StockMovementListResponse(BaseModel):
    items: list[ProductMovementResponse]
    total: int


class ProductAdjustmentCreate(BaseModel):
    counted_quantity: float = Field(ge=0)
    unit: str | None = Field(default=None, min_length=1, max_length=80)
    note: str | None = Field(default=None, max_length=500)
    occurred_at: datetime | None = None


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


class StockDocumentListResponse(BaseModel):
    items: list[StockDocumentResponse]
    total: int


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
    source: str = "open-meteo-model"


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

