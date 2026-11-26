"""Perishable lots derived from the stock ledger.

Every active receipt of a tracked product is a lot. Nothing is stored per lot except
owner overrides and waste records, so voiding a ledger movement always stays consistent.
"""
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import CropCycle, LotExpiryOverride, Product, ProductShelfLife, StockMovement, StockWaste, utc_now
from .products_stock import convert_quantity, record_movement, void_source_movements
from .secure_fields import encrypt_text, present_text_safe
from .source_types import CROP_CYCLE_HARVEST, STOCK_DOCUMENT, STOCK_WASTE

_BANGKOK = ZoneInfo("Asia/Bangkok")
_Q = Decimal("0.001")
_ZERO = Decimal("0")


class FreshnessConflict(Exception):
    """The request is valid but conflicts with current stock."""


def today_bangkok() -> date:
    return datetime.now(_BANGKOK).date()


def _local_date(value: datetime) -> date:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(_BANGKOK).date()


def _dec(value) -> Decimal:
    return Decimal(str(value)).quantize(_Q, rounding=ROUND_HALF_UP)


@dataclass
class Lot:
    key: str
    product_id: int
    received_on: date
    expires_on: date
    received: Decimal
    remaining: Decimal
    cycle_id: int | None
    expiry_overridden: bool
    wasted: Decimal = _ZERO

    def status(self, today: date, warn_days: int) -> str:
        if self.remaining <= 0:
            return "empty"
        if self.expires_on < today:
            return "expired"
        if (self.expires_on - today).days <= warn_days:
            return "expiring"
        return "fresh"


def lot_key(movement: StockMovement) -> str:
    # Harvest movements are re-created when the harvest is edited, so key them by cycle.
    if movement.source_type == CROP_CYCLE_HARVEST and movement.source_id is not None:
        return f"harvest-{movement.source_id}"
    return f"movement-{movement.id}"


def _take(lots: list[Lot], amount: Decimal, uses: list[tuple[Lot, Decimal]]) -> Decimal:
    for lot in lots:
        if amount <= 0:
            break
        used = min(lot.remaining, amount)
        if used > 0:
            lot.remaining -= used
            amount -= used
            uses.append((lot, used))
    return amount


def build_lots(db: Session, setting: ProductShelfLife) -> tuple[list[Lot], dict[int, list[tuple[Lot, Decimal]]], Decimal]:
    """Return lots, the lots used by each outgoing movement, and quantity not covered by any lot."""
    movements = db.scalars(
        select(StockMovement)
        .where(StockMovement.product_id == setting.product_id, StockMovement.voided_at.is_(None))
        .order_by(StockMovement.id)
    ).all()
    cycle_ids = [m.source_id for m in movements if m.source_type == CROP_CYCLE_HARVEST and m.source_id is not None]
    harvest_dates = dict(
        db.execute(select(CropCycle.id, CropCycle.harvest_date).where(CropCycle.id.in_(cycle_ids))).all()
    ) if cycle_ids else {}
    overrides = {
        row.lot_key: row.expires_on
        for row in db.scalars(select(LotExpiryOverride).where(LotExpiryOverride.product_id == setting.product_id))
    }
    waste_keys = {
        row.id: row.lot_key
        for row in db.scalars(select(StockWaste).where(
            StockWaste.product_id == setting.product_id, StockWaste.voided_at.is_(None)
        ))
    }

    lots: dict[str, Lot] = {}
    outgoing: list[StockMovement] = []
    for movement in movements:
        if movement.quantity_delta <= 0:
            outgoing.append(movement)
            continue
        key = lot_key(movement)
        is_harvest = movement.source_type == CROP_CYCLE_HARVEST
        received_on = (harvest_dates.get(movement.source_id) if is_harvest else None) or _local_date(movement.occurred_at)
        quantity = _dec(movement.quantity_delta)
        lots[key] = Lot(
            key=key,
            product_id=setting.product_id,
            received_on=received_on,
            expires_on=overrides.get(key) or received_on + timedelta(days=setting.shelf_life_days),
            received=quantity,
            remaining=quantity,
            cycle_id=movement.source_id if is_harvest else None,
            expiry_overridden=key in overrides,
        )

    ordered = sorted(lots.values(), key=lambda lot: (lot.expires_on, lot.received_on, lot.key))
    uses: dict[int, list[tuple[Lot, Decimal]]] = {}
    pending: list[tuple[StockMovement, Decimal]] = []

    # Waste names the physical lot it came from, so it is settled before anything is inferred.
    for movement in outgoing:
        amount = -_dec(movement.quantity_delta)
        used = uses.setdefault(movement.id, [])
        if movement.source_type == STOCK_WASTE:
            lot = lots.get(waste_keys.get(movement.source_id, ""))
            if lot is not None:
                before = lot.remaining
                amount = _take([lot], amount, used)
                lot.wasted += before - lot.remaining
        if amount > 0:
            pending.append((movement, amount))

    # First expired, first out among lots still good that day; expired stock is the last resort.
    leftovers: list[tuple[StockMovement, Decimal]] = []
    for movement, amount in sorted(pending, key=lambda row: (_local_date(row[0].occurred_at), row[0].id)):
        day = _local_date(movement.occurred_at)
        on_hand = [lot for lot in ordered if lot.received_on <= day]
        used = uses[movement.id]
        amount = _take([lot for lot in on_hand if lot.expires_on >= day], amount, used)
        amount = _take([lot for lot in on_hand if lot.expires_on < day], amount, used)
        if amount > 0:
            leftovers.append((movement, amount))
    # The ledger allows selling before receipt is recorded; settle that against later lots.
    uncovered = _ZERO
    for movement, amount in leftovers:
        uncovered += _take(ordered, amount, uses[movement.id])
    return ordered, uses, uncovered


def get_setting(db: Session, product_id: int) -> ProductShelfLife | None:
    return db.scalar(select(ProductShelfLife).where(ProductShelfLife.product_id == product_id))


def save_setting(db: Session, product_id: int, shelf_life_days: int, warn_days: int) -> ProductShelfLife:
    product = db.get(Product, product_id)
    if product is None or product.deleted_at is not None:
        raise ValueError("Product is not available")
    if warn_days > shelf_life_days:
        raise ValueError("Warning days exceed shelf life")
    setting = get_setting(db, product_id)
    if setting is None:
        setting = ProductShelfLife(product_id=product_id)
        db.add(setting)
    setting.shelf_life_days = shelf_life_days
    setting.warn_days = warn_days
    db.flush()
    return setting


def active_settings(db: Session, product_id: int | None = None) -> list[tuple[ProductShelfLife, Product]]:
    statement = (
        select(ProductShelfLife, Product)
        .join(Product, Product.id == ProductShelfLife.product_id)
        .where(Product.deleted_at.is_(None))
        .order_by(Product.id)
    )
    if product_id is not None:
        statement = statement.where(Product.id == product_id)
    return [tuple(row) for row in db.execute(statement).all()]


def find_lot(db: Session, product_id: int, key: str) -> tuple[ProductShelfLife, Lot]:
    setting = get_setting(db, product_id)
    if setting is not None:
        for lot in build_lots(db, setting)[0]:
            if lot.key == key:
                return setting, lot
    raise ValueError("Lot is not available")


def override_expiry(db: Session, product_id: int, key: str, expires_on: date, reason: str) -> None:
    _setting, lot = find_lot(db, product_id, key)
    if expires_on < lot.received_on:
        raise ValueError("Expiry date is before the lot date")
    row = db.scalar(select(LotExpiryOverride).where(
        LotExpiryOverride.product_id == product_id, LotExpiryOverride.lot_key == key
    ))
    if row is None:
        row = LotExpiryOverride(product_id=product_id, lot_key=key)
        db.add(row)
    row.expires_on = expires_on
    row.reason_encrypted = encrypt_text(reason.strip()).encode("ascii")
    db.flush()


def record_waste(db: Session, payload, created_by: int | None) -> StockWaste:
    _setting, lot = find_lot(db, payload.product_id, payload.lot_key)
    product = db.get(Product, payload.product_id)
    quantity = _dec(payload.quantity)
    if quantity <= 0:
        raise ValueError("Invalid quantity")
    if quantity > lot.remaining:
        raise FreshnessConflict("Waste is more than the lot's remaining quantity")
    waste = StockWaste(
        product_id=product.id,
        lot_key=lot.key,
        quantity=float(quantity),
        unit=product.unit,
        reason=payload.reason,
        note_encrypted=encrypt_text(payload.note.strip()).encode("ascii") if payload.note and payload.note.strip() else None,
        created_by=created_by,
    )
    db.add(waste)
    db.flush()
    record_movement(
        db, product.id, convert_quantity(-quantity, product.unit, product.unit), product.unit, "adjustment",
        source_type=STOCK_WASTE, source_id=waste.id,
    )
    return waste


def void_waste(db: Session, waste: StockWaste) -> None:
    if waste.voided_at is not None:
        raise FreshnessConflict("Waste record is already void")
    waste.voided_at = utc_now()
    void_source_movements(db, STOCK_WASTE, waste.id)
    db.flush()


def expired_lot_warnings(db: Session, document_id: int, product_ids: list[int]) -> list[str]:
    """Warn when an outbound document had to use lots past their date; never blocks the sale."""
    warnings = []
    for product_id in product_ids:
        setting = get_setting(db, product_id)
        if setting is None:
            continue
        uses = build_lots(db, setting)[1]
        movements = db.scalars(select(StockMovement).where(
            StockMovement.product_id == product_id,
            StockMovement.source_type == STOCK_DOCUMENT,
            StockMovement.source_id == document_id,
            StockMovement.voided_at.is_(None),
        )).all()
        if any(
            lot.expires_on < _local_date(movement.occurred_at)
            for movement in movements for lot, _used in uses.get(movement.id, [])
        ):
            warnings.append(f"expired_lot:{product_id}")
    return warnings


def present_product_name(product: Product, role):
    return present_text_safe(product.name_encrypted, role, table="products", row_id=product.id, field="name")


def present_waste(db: Session, waste: StockWaste, role) -> dict:
    product = db.get(Product, waste.product_id)
    name = present_product_name(product, role)
    note = present_text_safe(waste.note_encrypted, role, table="stock_waste", row_id=waste.id, field="note") if waste.note_encrypted else None
    return {
        "id": waste.id,
        "product_id": waste.product_id,
        "product_name": name.value,
        "lot_key": waste.lot_key,
        "quantity": waste.quantity,
        "unit": waste.unit,
        "reason": waste.reason,
        "note": note.value if note else None,
        "voided": waste.voided_at is not None,
        "created_at": waste.created_at if waste.created_at.tzinfo else waste.created_at.replace(tzinfo=UTC),
        "is_masked": role.value != "owner",
        "decrypt_failed": name.decrypt_failed or bool(note and note.decrypt_failed),
    }


def overview(db: Session, role, product_id: int | None, include_empty: bool) -> dict:
    today = today_bangkok()
    items, products = [], []
    counts = {"expired": 0, "expiring": 0}
    for setting, product in active_settings(db, product_id):
        lots, _uses, uncovered = build_lots(db, setting)
        name = present_product_name(product, role)
        products.append({
            "product_id": product.id,
            "product_name": name.value,
            "unit": product.unit,
            "shelf_life_days": setting.shelf_life_days,
            "warn_days": setting.warn_days,
            "uncovered_quantity": float(uncovered),
        })
        for lot in lots:
            status = lot.status(today, setting.warn_days)
            if status in counts:
                counts[status] += 1
            if status == "empty" and not include_empty:
                continue
            items.append({
                "lot_key": lot.key,
                "product_id": product.id,
                "product_name": name.value,
                "unit": product.unit,
                "cycle_id": lot.cycle_id,
                "received_on": lot.received_on,
                "expires_on": lot.expires_on,
                "days_left": (lot.expires_on - today).days,
                "received_quantity": float(lot.received),
                "remaining_quantity": float(lot.remaining),
                "wasted_quantity": float(lot.wasted),
                "expiry_overridden": lot.expiry_overridden,
                "status": status,
            })
    items.sort(key=lambda item: (item["status"] == "empty", item["expires_on"], item["product_id"], item["lot_key"]))
    return {"items": items, "products": products, "is_masked": role.value != "owner", **counts}
