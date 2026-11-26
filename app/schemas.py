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
    source_label: str | None = None
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


class ShelfLifeUpdate(BaseModel):
    shelf_life_days: int = Field(ge=0, le=3650)
    warn_days: int = Field(default=1, ge=0, le=3650)


class ShelfLifeResponse(ShelfLifeUpdate):
    model_config = ConfigDict(from_attributes=True)
    product_id: int


class FreshLotResponse(BaseModel):
    lot_key: str
    product_id: int
    product_name: str
    unit: str
    cycle_id: int | None
    received_on: date
    expires_on: date
    days_left: int
    received_quantity: float
    remaining_quantity: float
    wasted_quantity: float
    expiry_overridden: bool
    status: Literal["fresh", "expiring", "expired", "empty"]


class FreshProductResponse(BaseModel):
    product_id: int
    product_name: str
    unit: str
    shelf_life_days: int
    warn_days: int
    uncovered_quantity: float


class FreshnessOverviewResponse(BaseModel):
    items: list[FreshLotResponse]
    products: list[FreshProductResponse]
    expired: int
    expiring: int
    is_masked: bool


class LotExpiryUpdate(BaseModel):
    expires_on: date
    reason: str = Field(min_length=1, max_length=500, pattern=r"\S")


class StockWasteCreate(BaseModel):
    product_id: int = Field(gt=0)
    lot_key: str = Field(min_length=1, max_length=40)
    quantity: Decimal = Field(gt=0, le=1_000_000)
    reason: Literal["expired", "spoiled", "damaged", "pest", "other"]
    note: str | None = Field(default=None, max_length=1000)


class StockWasteResponse(BaseModel):
    id: int
    product_id: int
    product_name: str
    lot_key: str
    quantity: float
    unit: str
    reason: str
    note: str | None
    voided: bool
    created_at: datetime
    is_masked: bool
    decrypt_failed: bool


class StockWasteListResponse(BaseModel):
    items: list[StockWasteResponse]
    total: int


class SalesOrderLineInput(BaseModel):
    product_id: int = Field(gt=0)
    quantity: Decimal = Field(gt=0, le=1_000_000)
    unit: str | None = Field(default=None, max_length=80)
    delivery_date: date
    unit_price: Decimal | None = Field(default=None, ge=0, le=Decimal("99999999.99"))


class SalesOrderLineUpdate(SalesOrderLineInput):
    id: int | None = None


class SalesOrderCreate(BaseModel):
    customer_id: int = Field(gt=0)
    order_date: date | None = None
    safety_days: int = Field(default=0, ge=0, le=60)
    delivery_location: str | None = Field(default=None, max_length=500)
    note: str | None = Field(default=None, max_length=1000)
    auto_planting: bool = True
    lines: list[SalesOrderLineInput] = Field(min_length=1, max_length=100)


class SalesOrderUpdate(BaseModel):
    customer_id: int | None = Field(default=None, gt=0)
    safety_days: int | None = Field(default=None, ge=0, le=60)
    delivery_location: str | None = Field(default=None, max_length=500)
    note: str | None = Field(default=None, max_length=1000)
    auto_planting: bool | None = None
    lines: list[SalesOrderLineUpdate] | None = Field(default=None, min_length=1, max_length=100)


class SalesOrderClose(BaseModel):
    status: Literal["delivered", "cancelled"]


class SalesOrderDeliverLine(BaseModel):
    line_id: int = Field(gt=0)
    quantity: Decimal = Field(gt=0, le=1_000_000)
    unit_price: Decimal | None = Field(default=None, ge=0, le=Decimal("99999999.99"))
    use_order_price: bool = False


class SalesOrderDeliver(BaseModel):
    doc_date: date | None = None
    note: str | None = Field(default=None, max_length=500)
    record_finance: bool = True
    close_when_complete: bool = True
    lines: list[SalesOrderDeliverLine] = Field(min_length=1, max_length=100)


class SalesOrderLineResponse(BaseModel):
    id: int
    product_id: int
    product_name: str
    crop_name: str | None
    quantity: float
    unit: str
    delivery_date: date
    latest_sow_date: date | None
    planting_status: Literal["unmapped", "not_required", "waiting", "late", "ready", "planted", "covered", "manual", "delivered"]
    delivered_quantity: float
    unit_price: Decimal | str | None
    has_price: bool
    planting_ready: bool
    from_stock: float
    from_growing: float
    to_plant: float
    planting_task_id: int | None
    tables_needed: int | None
    cycle_ids: list[int]


class SalesOrderResponse(BaseModel):
    id: int
    order_no: str
    customer_id: int
    customer_name: str
    order_date: date
    safety_days: int
    delivery_location: str | None
    note: str | None
    status: str
    auto_planting: bool
    lines: list[SalesOrderLineResponse]
    is_masked: bool
    decrypt_failed: bool
    created_at: datetime


class SalesOrderDeliverResponse(BaseModel):
    order: SalesOrderResponse
    document_id: int
    doc_no: str
    warnings: list[str]


class SalesOrderListResponse(BaseModel):
    items: list[SalesOrderResponse]
    total: int


class PlantingProposalResponse(BaseModel):
    line_id: int
    order_no: str
    crop_name: str
    quantity: float
    unit: str
    to_plant: float
    delivery_date: date
    nursery_start: date
    expected_ready_date: date
    is_late: bool
    tables_needed: int | None
    free_tables: list[TableResponse]
    suggested_table_ids: list[int]
    can_create: bool


class PlantingCreate(BaseModel):
    table_ids: list[int] = Field(min_length=1, max_length=49)
    nursery_start: date
    create_tasks: bool = True


class PlantingCreateResponse(BaseModel):
    cycle_ids: list[int]


AutomationKey = Literal[
    "order_planting", "planting_cycles", "cycle_tasks", "harvest_stock",
    "order_fill", "outbound_finance", "inbound_finance", "order_close",
]


class AutomationPreferenceUpdate(BaseModel):
    mode: Literal["auto", "manual"]


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

