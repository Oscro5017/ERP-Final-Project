from datetime import UTC, date, datetime
from enum import Enum

from sqlalchemy import Boolean, Date, DateTime, Enum as SqlEnum, Float, ForeignKey, Index, Integer, LargeBinary, String, Text, UniqueConstraint, event, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class SoftDeleteMixin:
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)


class Role(str, Enum):
    owner = "owner"
    developer = "developer"


class CycleStatus(str, Enum):
    nursery = "nursery"
    bushed = "bushed"
    ready_to_harvest = "ready_to_harvest"
    harvested = "harvested"
    empty = "empty"


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    role: Mapped[Role] = mapped_column(SqlEnum(Role), default=Role.developer)


class SystemMeta(TimestampMixin, Base):
    __tablename__ = "system_meta"
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)


class Table(Base):
    __tablename__ = "tables"
    id: Mapped[int] = mapped_column(primary_key=True)
    table_number: Mapped[int] = mapped_column(Integer, unique=True)


class Batch(Base):
    __tablename__ = "batches"
    id: Mapped[int] = mapped_column(primary_key=True)
    batch_number: Mapped[int] = mapped_column(Integer, unique=True)
    start_date: Mapped[date] = mapped_column(Date)
    week_offset: Mapped[int] = mapped_column(Integer, default=0)


class CropType(Base):
    __tablename__ = "crop_types"
    __table_args__ = (Index("uq_crop_types_product_id", "product_id", unique=True),)
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    nursery_days: Mapped[int] = mapped_column(Integer)
    growth_days: Mapped[int] = mapped_column(Integer)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id", ondelete="SET NULL"), nullable=True)


class CropCycle(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "crop_cycles"
    id: Mapped[int] = mapped_column(primary_key=True)
    table_id: Mapped[int] = mapped_column(ForeignKey("tables.id"))
    batch_id: Mapped[int] = mapped_column(ForeignKey("batches.id"))
    crop_type_id: Mapped[int] = mapped_column(ForeignKey("crop_types.id"))
    nursery_start: Mapped[date] = mapped_column(Date)
    transplant_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    harvest_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[CycleStatus] = mapped_column(SqlEnum(CycleStatus), default=CycleStatus.nursery)
    cycle_code: Mapped[str] = mapped_column(String(6))
    harvest_quantity_kg: Mapped[float | None] = mapped_column(Float, nullable=True)

    table: Mapped[Table] = relationship()
    batch: Mapped[Batch] = relationship()
    crop_type: Mapped[CropType] = relationship()
    status_logs: Mapped[list["CropCycleStatusLog"]] = relationship(cascade="all, delete-orphan", order_by="CropCycleStatusLog.changed_at")


class CropCycleStatusLog(Base):
    __tablename__ = "crop_cycle_status_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    cycle_id: Mapped[int] = mapped_column(ForeignKey("crop_cycles.id"), index=True)
    from_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    to_status: Mapped[str] = mapped_column(String(32))
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


@event.listens_for(CropCycle, "before_insert")
@event.listens_for(CropCycle, "before_update")
def set_cycle_code(_mapper, _connection, target: CropCycle) -> None:
    if target.nursery_start:
        target.cycle_code = target.nursery_start.strftime("%y%m%d")


class Customer(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "customers"
    id: Mapped[int] = mapped_column(primary_key=True)
    name_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    contact_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    area_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)


class InputCatalog(Base):
    __tablename__ = "input_catalog"
    id: Mapped[int] = mapped_column(primary_key=True)
    name_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    name_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    last_unit: Mapped[str | None] = mapped_column(String(80), nullable=True)
    last_category: Mapped[str | None] = mapped_column(String(80), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(nullable=True)
    use_count: Mapped[int] = mapped_column(Integer, default=0)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id", ondelete="SET NULL"), nullable=True)


PRODUCT_CATEGORIES = ("vegetable", "seed", "fertilizer", "chemical", "blend", "other")
STOCK_MOVEMENT_TYPES = ("receipt", "shipment", "application", "adjustment")
STOCK_DOCUMENT_TYPES = ("inbound", "outbound")


class Product(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "products"
    __table_args__ = (
        Index("uq_products_name_hash_active", "name_hash", unique=True, sqlite_where=text("deleted_at IS NULL")),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    name_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    name_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    unit: Mapped[str] = mapped_column(String(80), nullable=False)
    reorder_point: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class StockMovement(TimestampMixin, Base):
    __tablename__ = "stock_movements"
    __table_args__ = (
        Index("ix_stock_movements_product_id", "product_id"),
        Index("ix_stock_movements_source", "source_type", "source_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    quantity_delta: Mapped[float] = mapped_column(Float, nullable=False)
    movement_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    source_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    note_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Supplier(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "suppliers"
    __table_args__ = (
        Index("ix_suppliers_name_hash", "name_hash"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    name_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    contact_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    area_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    note_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class StockDocument(TimestampMixin, Base):
    __tablename__ = "stock_documents"
    __table_args__ = (UniqueConstraint("doc_no", name="uq_stock_documents_doc_no"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    doc_no: Mapped[str] = mapped_column(String(32), nullable=False)
    doc_type: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    doc_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=True, index=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id", ondelete="RESTRICT"), nullable=True, index=True)
    crop_cycle_id: Mapped[int | None] = mapped_column(ForeignKey("crop_cycles.id", ondelete="RESTRICT"), nullable=True, index=True)
    reference_no: Mapped[str | None] = mapped_column(String(120), nullable=True)
    note_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="posted", nullable=False, index=True)
    void_reason_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class StockDocumentLine(TimestampMixin, Base):
    __tablename__ = "stock_document_lines"
    __table_args__ = (
        UniqueConstraint("document_id", "line_no", name="uq_stock_document_lines_line_no"),
        Index("ix_stock_document_lines_product_id", "product_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("stock_documents.id", ondelete="RESTRICT"), nullable=False, index=True)
    line_no: Mapped[int] = mapped_column(Integer, nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(80), nullable=False)
    unit_price_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    line_amount_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)


FINANCE_CATEGORIES = ("sale", "purchase", "labor", "utilities", "equipment", "transport", "other")
FINANCE_DIRECTIONS = ("income", "expense")


class FinanceEntry(TimestampMixin, Base):
    __tablename__ = "finance_entries"
    __table_args__ = (
        Index("ix_finance_entries_date_status", "entry_date", "status"),
        Index("ix_finance_entries_source", "source_type", "source_id", "is_auto", "status"),
        Index(
            "uq_finance_entries_auto_posted_source",
            "source_type", "source_id",
            unique=True,
            sqlite_where=text("is_auto = 1 AND status = 'posted' AND source_id IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    entry_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    amount_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    description_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    source_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    source_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    crop_cycle_id: Mapped[int | None] = mapped_column(ForeignKey("crop_cycles.id", ondelete="RESTRICT"), nullable=True, index=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id", ondelete="RESTRICT"), nullable=True, index=True)
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=True, index=True)
    is_auto: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="posted", nullable=False)
    void_reason_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class InputApplication(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "input_applications"
    id: Mapped[int] = mapped_column(primary_key=True)
    cycle_id: Mapped[int] = mapped_column(ForeignKey("crop_cycles.id"), index=True)
    applied_date: Mapped[date] = mapped_column(Date)
    category: Mapped[str] = mapped_column(String(80), default="")
    note_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)

    cycle: Mapped[CropCycle] = relationship(backref="input_applications")
    items: Mapped[list["InputItem"]] = relationship(cascade="all, delete-orphan", back_populates="application")


class InputItem(TimestampMixin, Base):
    __tablename__ = "input_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("input_applications.id"), index=True)
    item_name_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    quantity_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    unit: Mapped[str] = mapped_column(String(80), default="")
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id", ondelete="SET NULL"), nullable=True)

    application: Mapped[InputApplication] = relationship(back_populates="items")


class TaskStatus(str, Enum):
    pending = "pending"
    done = "done"


class TaskSource(str, Enum):
    auto = "auto"
    manual = "manual"


class Task(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "tasks"
    __table_args__ = (
        Index(
            "uq_tasks_open_stock_alert",
            "stock_alert_product_id",
            unique=True,
            sqlite_where=text("stock_alert_product_id IS NOT NULL AND status = 'pending' AND deleted_at IS NULL"),
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    cycle_id: Mapped[int | None] = mapped_column(ForeignKey("crop_cycles.id", ondelete="CASCADE"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(Text)
    due_date: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(String(20), default=TaskStatus.pending.value, index=True)
    source: Mapped[str] = mapped_column(String(20), default=TaskSource.manual.value)
    is_encrypted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    labor_cost_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    worker_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    extra_cost_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    stock_alert_product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id", ondelete="SET NULL"), nullable=True)
    cycle: Mapped[CropCycle | None] = relationship(backref="tasks")


class WeatherLog(TimestampMixin, Base):
    __tablename__ = "weather_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    log_date: Mapped[date] = mapped_column(Date, unique=True, index=True)
    temp_min: Mapped[float] = mapped_column(Float)
    temp_max: Mapped[float] = mapped_column(Float)
    humidity: Mapped[float] = mapped_column(Float)
    rainfall: Mapped[float] = mapped_column(Float)
    condition: Mapped[str] = mapped_column(String(100))
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ForecastSnapshot(Base):
    __tablename__ = "forecast_snapshots"
    __table_args__ = (UniqueConstraint("issued_date", "target_date", "source", name="uq_forecast_snapshot_issue_target_source"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    issued_date: Mapped[date] = mapped_column(Date, nullable=False)
    target_date: Mapped[date] = mapped_column(Date, nullable=False)
    lead_days: Mapped[int] = mapped_column(Integer, nullable=False)
    temp_min: Mapped[float] = mapped_column(Float, nullable=False)
    temp_max: Mapped[float] = mapped_column(Float, nullable=False)
    humidity: Mapped[float] = mapped_column(Float, nullable=False)
    precip_probability: Mapped[float] = mapped_column(Float, nullable=False)
    precip_mm: Mapped[float] = mapped_column(Float, nullable=False)
    condition: Mapped[str] = mapped_column(String(100), nullable=False)
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class SensorReading(Base):
    __tablename__ = "sensor_readings"
    __table_args__ = (
        UniqueConstraint("device_id", "sensor_type", "recorded_at", name="uq_sensor_device_type_recorded"),
        Index("ix_sensor_type_recorded_at", "sensor_type", "recorded_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[str] = mapped_column(String(100), nullable=False)
    sensor_type: Mapped[str] = mapped_column(String(40), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class Recommendation(TimestampMixin, Base):
    """Future messages must refer to input categories, never disclose fertilizer names."""

    __tablename__ = "recommendations"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    window_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    window_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id"), nullable=True)


class Insight(TimestampMixin, Base):
    __tablename__ = "insights"
    __table_args__ = (
        Index("ix_insights_status_valid_from", "status", "valid_from"),
        UniqueConstraint("legacy_recommendation_id", name="uq_insights_legacy_recommendation"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    source: Mapped[str] = mapped_column(String(24), nullable=False)
    title_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    body_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    severity: Mapped[str] = mapped_column(String(24), default="info", nullable=False)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    crop_cycle_id: Mapped[int | None] = mapped_column(ForeignKey("crop_cycles.id", ondelete="SET NULL"), nullable=True)
    task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="new", nullable=False)
    legacy_recommendation_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

