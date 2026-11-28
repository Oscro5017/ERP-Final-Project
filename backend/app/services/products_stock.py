from datetime import UTC, date, datetime, time
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from ..models import Product, StockMovement, Activity, STOCK_MOVEMENT_TYPES, utc_now
from .secure_fields import encrypt_text, safe_decrypt_text

_Q = Decimal("0.001")
_BANGKOK = ZoneInfo("Asia/Bangkok")


def start_of_day(day: date) -> datetime:
    """Farm-local midnight of a date, in UTC: the time given to stock moved on a stated day."""
    return datetime.combine(day, time.min, tzinfo=_BANGKOK).astimezone(UTC)


def same_moment(first: datetime, second: datetime) -> bool:
    # SQLite returns naive UTC values, so compare both as naive UTC.
    def naive(value: datetime) -> datetime:
        return value.astimezone(UTC).replace(tzinfo=None) if value.tzinfo else value

    return naive(first) == naive(second)
_UNIT_ALIASES = {
    "kg": ("mass", Decimal("1")), "กก.": ("mass", Decimal("1")), "กิโลกรัม": ("mass", Decimal("1")),
    "g": ("mass", Decimal("0.001")), "กรัม": ("mass", Decimal("0.001")),
    "l": ("volume", Decimal("1")), "ลิตร": ("volume", Decimal("1")),
    "ml": ("volume", Decimal("0.001")), "มล.": ("volume", Decimal("0.001")), "มิลลิลิตร": ("volume", Decimal("0.001")),
}


def _decimal(value) -> Decimal:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("Invalid quantity or unit") from exc
    if not number.is_finite():
        raise ValueError("Invalid quantity or unit")
    return number


def convert_quantity(quantity, unit: str, base_unit: str) -> float:
    qty = _decimal(quantity)
    source_key = (unit or "").strip().casefold()
    base_key = (base_unit or "").strip().casefold()
    source = _UNIT_ALIASES.get(source_key)
    base = _UNIT_ALIASES.get(base_key)
    if source or base:
        if not source or not base or source[0] != base[0]:
            raise ValueError("Invalid quantity or unit")
        result = qty * source[1] / base[1]
    elif source_key == base_key and source_key:
        result = qty
    else:
        raise ValueError("Invalid quantity or unit")
    return float(result.quantize(_Q, rounding=ROUND_HALF_UP))


def on_hand(db: Session, product_id: int) -> float:
    value = db.scalar(
        select(func.coalesce(func.sum(StockMovement.quantity_delta), 0.0)).where(
            StockMovement.product_id == product_id, StockMovement.voided_at.is_(None)
        )
    )
    return round(float(value or 0), 3)


def on_hand_grouped(db: Session, product_ids: list[int] | None = None) -> dict[int, float]:
    statement = select(StockMovement.product_id, func.sum(StockMovement.quantity_delta)).where(
        StockMovement.voided_at.is_(None)
    ).group_by(StockMovement.product_id)
    if product_ids is not None:
        if not product_ids:
            return {}
        statement = statement.where(StockMovement.product_id.in_(product_ids))
    return {pid: round(float(total or 0), 3) for pid, total in db.execute(statement)}


def record_movement(
    db: Session, product_id: int, quantity, unit: str, movement_type: str,
    source_type: str | None = None, source_id: int | None = None,
    occurred_at: datetime | None = None, note: str | None = None,
) -> StockMovement:
    if movement_type not in STOCK_MOVEMENT_TYPES:
        raise ValueError("Invalid movement type")
    product = db.get(Product, product_id)
    if product is None or product.deleted_at is not None:
        raise ValueError("Product not found")
    delta = convert_quantity(quantity, unit, product.unit)
    if (
        (movement_type == "receipt" and delta <= 0)
        or (movement_type in {"shipment", "application"} and delta >= 0)
        or (movement_type == "adjustment" and delta == 0)
    ):
        raise ValueError("Invalid quantity or movement type")
    movement = StockMovement(
        product_id=product_id, quantity_delta=delta, movement_type=movement_type,
        source_type=source_type, source_id=source_id, occurred_at=occurred_at or utc_now(),
        note_encrypted=encrypt_text(note).encode("ascii") if note else None,
    )
    db.add(movement)
    db.flush()
    sync_product_low_stock_reminder(db, product)
    return movement


def sync_product_low_stock_reminder(db: Session, product: Product) -> None:
    alerts = db.scalars(select(Activity).where(
        Activity.stock_alert_product_id == product.id,
        Activity.status == "pending",
        Activity.deleted_at.is_(None),
    )).all()
    if product.reorder_point is None:
        for task in alerts:
            task.status = "done"
        if alerts:
            db.flush()
        return
    balance = on_hand(db, product.id)
    if balance <= product.reorder_point:
        if alerts:
            return
        name = safe_decrypt_text(product.name_encrypted, table="products", row_id=product.id, field="name")
        db.add(Activity(
            title=encrypt_text(f"ของใกล้หมด: {name.value}" if not name.decrypt_failed else f"ของใกล้หมด #{product.id}"),
            kind="stock_alert",
            remind=True,
            planned_date=datetime.now(_BANGKOK).date(),
            status="pending",
            source="auto",
            is_encrypted=True,
            stock_alert_product_id=product.id,
        ))
        db.flush()
        return
    for task in alerts:
        task.status = "done"
    if alerts:
        db.flush()


def void_source_movements(db: Session, source_type: str, source_id: int) -> int:
    product_ids = db.scalars(select(StockMovement.product_id).where(
        StockMovement.source_type == source_type,
        StockMovement.source_id == source_id,
        StockMovement.voided_at.is_(None),
    ).distinct()).all()
    result = db.execute(
        update(StockMovement).where(
            StockMovement.source_type == source_type,
            StockMovement.source_id == source_id,
            StockMovement.voided_at.is_(None),
        ).values(voided_at=utc_now())
    )
    voided = int(result.rowcount or 0)
    for product_id in product_ids:
        product = db.get(Product, product_id)
        if product is not None and product.deleted_at is None:
            sync_product_low_stock_reminder(db, product)
    return voided
