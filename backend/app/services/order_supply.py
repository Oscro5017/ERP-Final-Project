"""Match open order lines with fresh stock and growing cycles to find what still needs planting.

Shared supply is only counted for products with a shelf-life setting, because without one
there is no way to know that today's stock will still be good on the delivery date.
"""
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import (
    CropCycle,
    CropType,
    CycleStatus,
    Product,
    SalesOrder,
    SalesOrderCycle,
    SalesOrderDelivery,
    SalesOrderLine,
    StockDocument,
)
from ..query_helpers import active_rows
from .freshness import build_lots, get_setting
from .products_stock import convert_quantity

_BANGKOK = ZoneInfo("Asia/Bangkok")
_Q = Decimal("0.001")
_ZERO = Decimal("0")
_YIELD_SAMPLE = 20
_GROWING = (CycleStatus.nursery, CycleStatus.bushed, CycleStatus.ready_to_harvest)


def today_bangkok() -> date:
    return datetime.now(_BANGKOK).date()


def _dec(value) -> Decimal:
    return Decimal(str(value)).quantize(_Q, rounding=ROUND_HALF_UP)


@dataclass
class Coverage:
    """Quantities are in the order line's unit."""
    delivered: float = 0.0
    from_stock: float = 0.0
    from_growing: float = 0.0
    to_plant: float = 0.0


@dataclass
class _Source:
    kind: str  # "stock" or "growing"
    remaining: Decimal
    available_from: date
    good_until: date | None
    owner_line_id: int | None = None


@dataclass
class _Demand:
    line: SalesOrderLine
    order: SalesOrder
    needed: Decimal
    target: date
    used: dict[str, Decimal] = field(default_factory=lambda: {"stock": _ZERO, "growing": _ZERO})


def delivered_quantity(db: Session, line_id: int) -> float:
    value = db.scalar(
        select(func.coalesce(func.sum(SalesOrderDelivery.quantity), 0.0))
        .join(StockDocument, StockDocument.id == SalesOrderDelivery.document_id)
        .where(SalesOrderDelivery.line_id == line_id, StockDocument.status == "posted")
    )
    return round(float(value or 0), 3)


def average_yield_kg(db: Session, crop_type_id: int) -> float | None:
    statement = select(CropCycle.harvest_quantity_kg).where(
        CropCycle.crop_type_id == crop_type_id, CropCycle.harvest_quantity_kg > 0
    )
    statement = active_rows(statement, CropCycle).order_by(
        CropCycle.harvest_date.desc(), CropCycle.id.desc()
    ).limit(_YIELD_SAMPLE)
    values = db.scalars(statement).all()
    return sum(values) / len(values) if values else None


def _in_product_unit(kilograms: float | None, product: Product) -> Decimal | None:
    if kilograms is None:
        return None
    try:
        return _dec(convert_quantity(kilograms, "kg", product.unit))
    except ValueError:
        return None


def _ready_date(cycle: CropCycle, crop_type: CropType, today: date) -> date:
    if cycle.status == CycleStatus.ready_to_harvest:
        return today
    transplanted = cycle.transplant_date or cycle.nursery_start + timedelta(days=crop_type.nursery_days)
    return max(today, transplanted + timedelta(days=crop_type.growth_days))


def _take(demand: _Demand, sources: list[_Source]) -> None:
    for source in sources:
        if demand.needed <= 0:
            return
        used = min(source.remaining, demand.needed)
        if used > 0:
            source.remaining -= used
            demand.needed -= used
            demand.used[source.kind] += used


def _fits(source: _Source, demand: _Demand) -> bool:
    latest = demand.target
    if source.kind == "growing":
        # Extra safety days apply to crops that still have to be harvested.
        latest = demand.target - timedelta(days=demand.order.safety_days)
    return source.available_from <= latest and (
        source.good_until is None or source.good_until >= demand.target
    )


def product_coverage(db: Session, product: Product) -> dict[int, Coverage]:
    """Coverage of every open order line of one product."""
    today = today_bangkok()
    rows = db.execute(
        select(SalesOrder, SalesOrderLine)
        .join(SalesOrderLine, SalesOrderLine.order_id == SalesOrder.id)
        .where(SalesOrder.status == "open", SalesOrderLine.product_id == product.id)
        .order_by(SalesOrderLine.delivery_date, SalesOrder.id, SalesOrderLine.id)
    ).all()
    crop_type = db.scalar(select(CropType).where(CropType.product_id == product.id))
    results: dict[int, Coverage] = {}
    demands: list[_Demand] = []
    for order, line in rows:
        delivered = delivered_quantity(db, line.id)
        results[line.id] = Coverage(delivered=delivered)
        outstanding = max(_ZERO, _dec(line.quantity) - _dec(delivered))
        if outstanding > 0:
            needed = _dec(convert_quantity(outstanding, line.unit, product.unit))
            demands.append(_Demand(line, order, needed, max(line.delivery_date, today)))

    setting = get_setting(db, product.id)
    open_lines = [line.id for _order, line in rows]
    owners = dict(db.execute(
        select(SalesOrderCycle.cycle_id, SalesOrderCycle.line_id).where(SalesOrderCycle.line_id.in_(open_lines))
    ).all()) if open_lines else {}
    sources: list[_Source] = []
    covered_by_unknown: set[int] = set()

    if setting is not None:
        for lot in build_lots(db, setting)[0]:
            if lot.remaining > 0 and lot.expires_on >= today:
                sources.append(_Source(
                    "stock", lot.remaining, lot.received_on, lot.expires_on, owners.get(lot.cycle_id)
                ))
    if crop_type is not None:
        average = _in_product_unit(average_yield_kg(db, crop_type.id), product)
        cycles = db.scalars(
            select(CropCycle)
            .where(CropCycle.crop_type_id == crop_type.id, CropCycle.deleted_at.is_(None))
            .order_by(CropCycle.id)
        ).all()
        for cycle in cycles:
            owner = owners.get(cycle.id)
            if cycle.status in _GROWING:
                if average is None:
                    # Cycles created for a line are trusted to cover it until a yield is known.
                    if owner is not None:
                        covered_by_unknown.add(owner)
                elif owner is not None or setting is not None:
                    ready = _ready_date(cycle, crop_type, today)
                    good_until = ready + timedelta(days=setting.shelf_life_days) if setting else None
                    sources.append(_Source("growing", average, ready, good_until, owner))
            elif owner is not None and setting is None and cycle.status == CycleStatus.harvested:
                harvested = _in_product_unit(cycle.harvest_quantity_kg, product)
                if harvested:
                    sources.append(_Source("stock", harvested, today, None, owner))

    # Cycles planted for a line serve that line first; only their surplus is shared.
    for demand in demands:
        _take(demand, [
            source for source in sources
            if source.owner_line_id == demand.line.id and (source.kind == "growing" or _fits(source, demand))
        ])
    if setting is not None:
        sources.sort(key=lambda source: (source.kind != "stock", source.good_until or date.max, source.available_from))
        for demand in demands:
            if demand.line.id not in covered_by_unknown:
                _take(demand, [source for source in sources if _fits(source, demand)])

    for demand in demands:
        coverage = results[demand.line.id]

        def in_line_unit(value: Decimal) -> float:
            return convert_quantity(value, product.unit, demand.line.unit)

        coverage.from_stock = in_line_unit(demand.used["stock"])
        if demand.line.id in covered_by_unknown:
            coverage.from_growing = in_line_unit(demand.used["growing"] + demand.needed)
        else:
            coverage.from_growing = in_line_unit(demand.used["growing"])
            coverage.to_plant = in_line_unit(demand.needed)
    return results


def open_coverage(db: Session) -> dict[int, Coverage]:
    """Coverage of every open order line."""
    products = db.scalars(
        select(Product).where(Product.id.in_(
            select(SalesOrderLine.product_id)
            .join(SalesOrder, SalesOrder.id == SalesOrderLine.order_id)
            .where(SalesOrder.status == "open")
        ))
    ).all()
    results: dict[int, Coverage] = {}
    for product in products:
        results.update(product_coverage(db, product))
    return results
