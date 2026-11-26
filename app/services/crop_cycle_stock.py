from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import CropCycle, CropType, Product, StockMovement
from .crop_cycle_options import cycle_option
from .products_stock import convert_quantity, record_movement, void_source_movements
from .source_types import CROP_CYCLE_HARVEST

_KG_UNITS = {"kg", "กก.", "กิโลกรัม"}


def sync_crop_cycle_harvest_stock(db: Session, cycle: CropCycle) -> list[str]:
    """Keep the crop cycle's harvest quantity represented by one active stock movement."""
    current = db.scalars(select(StockMovement).where(
        StockMovement.source_type == CROP_CYCLE_HARVEST,
        StockMovement.source_id == cycle.id,
        StockMovement.voided_at.is_(None),
    ).order_by(StockMovement.id)).all()

    quantity = cycle.harvest_quantity_kg
    opted_out = not cycle_option(db, cycle.id, "record_harvest_stock")
    if cycle.deleted_at is not None or quantity is None or quantity <= 0 or opted_out:
        if current:
            void_source_movements(db, CROP_CYCLE_HARVEST, cycle.id)
        return []

    crop_type = db.get(CropType, cycle.crop_type_id)
    product_id = crop_type.product_id if crop_type else None
    if product_id is None:
        if current:
            void_source_movements(db, CROP_CYCLE_HARVEST, cycle.id)
        return ["no_product_mapping"]

    product = db.get(Product, product_id)
    if product is None or product.deleted_at is not None or not product.is_active:
        if current:
            void_source_movements(db, CROP_CYCLE_HARVEST, cycle.id)
        return ["no_product_mapping"]
    if (product.unit or "").strip().casefold() not in _KG_UNITS:
        if current:
            void_source_movements(db, CROP_CYCLE_HARVEST, cycle.id)
        return [f"unit_mismatch:{product.id}"]

    try:
        amount = Decimal(str(quantity))
        if not amount.is_finite() or amount <= 0:
            raise ValueError("Invalid harvest quantity")
        normalized = convert_quantity(amount, "kg", product.unit)
    except (InvalidOperation, ValueError, TypeError):
        if current:
            void_source_movements(db, CROP_CYCLE_HARVEST, cycle.id)
        return [f"unit_mismatch:{product.id}"]

    if len(current) == 1:
        movement = current[0]
        if movement.product_id == product.id and movement.movement_type == "receipt" and movement.quantity_delta == normalized:
            return []

    if current:
        void_source_movements(db, CROP_CYCLE_HARVEST, cycle.id)
    record_movement(
        db,
        product.id,
        normalized,
        product.unit,
        "receipt",
        source_type=CROP_CYCLE_HARVEST,
        source_id=cycle.id,
    )
    return []
