"""Harvests enter stock: one receipt per harvest entry, on the day it was picked.

A cycle picked over several days has several entries, and each becomes its own
fresh-produce lot. The cycle's ``harvest_quantity_kg`` is kept as the running total.
"""
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import CropCycle, CropType, HarvestEntry, Product, StockMovement
from .crop_cycle_options import cycle_option
from .products_stock import convert_quantity, record_movement, same_moment, start_of_day, void_source_movements
from .source_types import CROP_CYCLE_HARVEST, HARVEST_ENTRY

_KG_UNITS = {"kg", "กก.", "กิโลกรัม"}


def active_entries(db: Session, cycle_id: int) -> list[HarvestEntry]:
    return db.scalars(select(HarvestEntry).where(
        HarvestEntry.crop_cycle_id == cycle_id, HarvestEntry.voided_at.is_(None)
    ).order_by(HarvestEntry.harvested_on, HarvestEntry.id)).all()


def _harvest_product(db: Session, cycle: CropCycle) -> tuple[Product | None, str | None]:
    crop_type = db.get(CropType, cycle.crop_type_id)
    product = db.get(Product, crop_type.product_id) if crop_type and crop_type.product_id else None
    if product is None or product.deleted_at is not None or not product.is_active:
        return None, "no_product_mapping"
    if (product.unit or "").strip().casefold() not in _KG_UNITS:
        return None, f"unit_mismatch:{product.id}"
    return product, None


def _sync_entry(db: Session, cycle: CropCycle, entry: HarvestEntry, product: Product | None) -> None:
    current = db.scalars(select(StockMovement).where(
        StockMovement.source_type == HARVEST_ENTRY,
        StockMovement.source_id == entry.id,
        StockMovement.voided_at.is_(None),
    )).all()
    wanted = None
    if product is not None and entry.voided_at is None and entry.quantity_kg > 0:
        try:
            amount = Decimal(str(entry.quantity_kg))
            wanted = convert_quantity(amount, "kg", product.unit) if amount.is_finite() else None
        except (InvalidOperation, ValueError, TypeError):
            wanted = None
    occurred_at = start_of_day(entry.harvested_on)
    if (
        wanted is not None and len(current) == 1 and current[0].product_id == product.id
        and current[0].quantity_delta == wanted and same_moment(current[0].occurred_at, occurred_at)
    ):
        return
    if current:
        void_source_movements(db, HARVEST_ENTRY, entry.id)
    if wanted:
        record_movement(
            db, product.id, wanted, product.unit, "receipt",
            source_type=HARVEST_ENTRY, source_id=entry.id, occurred_at=occurred_at,
        )


def sync_crop_cycle_harvest_stock(db: Session, cycle: CropCycle) -> list[str]:
    """Keep every harvest entry of the cycle represented by one active receipt."""
    db.flush()
    entries = db.scalars(select(HarvestEntry).where(HarvestEntry.crop_cycle_id == cycle.id)).all()
    # Receipts from before harvest entries existed are replaced by the entries' own.
    void_source_movements(db, CROP_CYCLE_HARVEST, cycle.id)
    product, warning = (None, None)
    if cycle.deleted_at is None and cycle_option(db, cycle.id, "record_harvest_stock"):
        if any(entry.voided_at is None for entry in entries):
            product, warning = _harvest_product(db, cycle)
    for entry in entries:
        _sync_entry(db, cycle, entry, product if cycle.deleted_at is None else None)
    return [warning] if warning else []
