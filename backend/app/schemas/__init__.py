"""Request and response models, one module per feature.

Everything is re-exported here so routers can keep importing from `app.schemas`.
"""
from .common import DecryptionStatusResponse
from .auth import LoginRequest, TokenResponse
from .farm import (
    TableResponse,
    BatchResponse,
    CropTypeResponse,
    CropTypeProductMappingUpdate,
    CropTypeUpdate,
    CropCycleStatusChange,
    HarvestEntryCreate,
    HarvestEntryResponse,
    CropCycleCreate,
    CropCycleUpdate,
    CropCycleResponse,
    CropCycleStatusLogResponse,
)
from .inputs import InputCatalogSuggestionResponse, InputCatalogSuggestionsResponse
from .activities import (
    ActivityItemInput,
    ActivityShareInput,
    ActivityCreate,
    ActivityUpdate,
    ActivityStatusChange,
    ActivityTargetResponse,
    ActivityItemResponse,
    ActivityResponse,
    ChangeNoteResponse,
)
from .tasks import TaskCreate, TaskUpdate, TaskCycleInfo, TaskResponse
from .partners import (
    CustomerCreate,
    CustomerUpdate,
    CustomerResponse,
    SupplierCreate,
    SupplierUpdate,
    SupplierResponse,
    SupplierListResponse,
)
from .stock import (
    ProductCreate,
    ProductUpdate,
    ProductResponse,
    ProductListResponse,
    StockBalanceResponse,
    StockBalanceListResponse,
    ProductMovementResponse,
    StockMovementListResponse,
    ProductAdjustmentCreate,
)
from .stock_documents import (
    StockDocumentLineCreate,
    StockDocumentLineResponse,
    InboundDocumentCreate,
    OutboundDocumentCreate,
    StockDocumentUpdate,
    StockDocumentVoidRequest,
    StockDocumentResponse,
    LastPriceResponse,
    StockDocumentListResponse,
)
from .freshness import (
    ShelfLifeUpdate,
    ShelfLifeResponse,
    FreshLotResponse,
    FreshProductResponse,
    FreshnessOverviewResponse,
    LotExpiryUpdate,
    StockWasteCreate,
    StockWasteResponse,
    StockWasteListResponse,
)
from .finance import (
    FinanceEntryCreate,
    FinanceEntryUpdate,
    FinanceEntryVoidRequest,
    FinanceEntryResponse,
    FinanceEntryListResponse,
    InsightStatusUpdate,
    InsightResponse,
)
from .sales_orders import (
    SalesOrderLineInput,
    SalesOrderLineUpdate,
    SalesOrderCreate,
    SalesOrderUpdate,
    SalesOrderClose,
    SalesOrderDeliverLine,
    SalesOrderDeliver,
    SalesOrderLineResponse,
    SalesOrderResponse,
    SalesOrderDeliverResponse,
    SalesOrderListResponse,
    PlantingProposalResponse,
    PlantingCreate,
    PlantingCreateResponse,
)
from .preferences import AutomationKey, AutomationPreferenceUpdate
from .weather import (
    WeatherForecastDay,
    WeatherLogResponse,
    WeatherSyncResponse,
    SensorReadingInput,
    SensorReadingsCreate,
    SensorReadingResponse,
    SensorReadingsAccepted,
)
