import math
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    DEFAULT_TABLE_CAPACITY,
    Batch,
    CropCycle,
    CropType,
    Customer,
    CycleStatus,
    Product,
    SalesOrder,
    SalesOrderCycle,
    SalesOrderDelivery,
    SalesOrderLine,
    SalesOrderLinePrice,
    SalesOrderOption,
    Table,
    Activity,
    utc_now,
)
from ..query_helpers import get_active
from ..schemas import OutboundDocumentCreate
from .crop_cycle_options import save_cycle_options
from .crop_production import start_cycle
from .finance_entries import create_auto_finance_for_document
from .order_supply import Coverage, average_yield_kg, average_yield_per_plant_kg, delivered_quantity, open_coverage
from .table_space import free_table_spaces
from .products_stock import convert_quantity
from .secure_fields import encrypt_number, encrypt_text, present_number_safe, present_text_safe, safe_decrypt_number
from .stock_documents import create_stock_document, set_document_purpose
from .task_finance import void_task_finance

_BANGKOK = ZoneInfo("Asia/Bangkok")
_QUANTITY = Decimal("0.001")


class OrderConflict(Exception):
    """The request is valid but conflicts with the current state."""


def today_bangkok() -> date:
    return datetime.now(_BANGKOK).date()


def latest_sow_date(delivery_date: date, crop_type: CropType, safety_days: int) -> date:
    return delivery_date - timedelta(days=crop_type.nursery_days + crop_type.growth_days + safety_days)


def _next_order_no(db: Session, order_date: date) -> str:
    prefix = f"SO-{order_date:%y%m%d}-"
    existing = db.scalars(select(SalesOrder.order_no).where(SalesOrder.order_no.like(prefix + "%"))).all()
    return f"{prefix}{max((int(value.rsplit('-', 1)[1]) for value in existing), default=0) + 1:03d}"


def _encrypt(value: str | None) -> bytes | None:
    value = (value or "").strip()
    return encrypt_text(value).encode("ascii") if value else None


def _crop_type_for(db: Session, product_id: int) -> CropType | None:
    return db.scalar(select(CropType).where(CropType.product_id == product_id))


def auto_planting(db: Session, order_id: int) -> bool:
    value = db.scalar(select(SalesOrderOption.auto_planting).where(SalesOrderOption.order_id == order_id))
    return True if value is None else value


def _set_auto_planting(db: Session, order_id: int, value: bool) -> None:
    row = db.scalar(select(SalesOrderOption).where(SalesOrderOption.order_id == order_id))
    if row is None:
        if value:
            return
        row = SalesOrderOption(order_id=order_id)
        db.add(row)
    row.auto_planting = value
    db.flush()


def _line_price(db: Session, line_id: int) -> SalesOrderLinePrice | None:
    return db.scalar(select(SalesOrderLinePrice).where(SalesOrderLinePrice.line_id == line_id))


def _set_line_price(db: Session, line_id: int, value: Decimal | None) -> None:
    row = _line_price(db, line_id)
    if value is None:
        if row is not None:
            db.delete(row)
            db.flush()
        return
    if row is None:
        row = SalesOrderLinePrice(line_id=line_id)
        db.add(row)
    row.unit_price_encrypted = encrypt_number(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)).encode("ascii")
    db.flush()


def _agreed_price(db: Session, line_id: int) -> Decimal | None:
    row = _line_price(db, line_id)
    if row is None:
        return None
    price = safe_decrypt_number(
        row.unit_price_encrypted, table="sales_order_line_prices", row_id=row.id, field="unit_price"
    )
    if price.decrypt_failed:
        raise OrderConflict("Agreed price cannot be read")
    return price.value


def active_cycles(db: Session, line_id: int) -> list[CropCycle]:
    return list(db.scalars(
        select(CropCycle)
        .join(SalesOrderCycle, SalesOrderCycle.cycle_id == CropCycle.id)
        .where(SalesOrderCycle.line_id == line_id, CropCycle.deleted_at.is_(None))
        .order_by(CropCycle.id)
    ).all())


def _planting_task(db: Session, line: SalesOrderLine) -> Activity | None:
    return get_active(db, Activity, line.planting_task_id) if line.planting_task_id is not None else None


def _drop_pending_task(db: Session, line: SalesOrderLine) -> None:
    task = _planting_task(db, line)
    if task is not None and task.status == "pending":
        task.deleted_at = utc_now()
        void_task_finance(db, task.id)
        line.planting_task_id = None


def _sync_line_planting(db: Session, order: SalesOrder, line: SalesOrderLine, to_plant: float) -> None:
    """Recompute the latest sowing date and keep one planting task in step with it."""
    crop_type = _crop_type_for(db, line.product_id)
    line.latest_sow_date = latest_sow_date(line.delivery_date, crop_type, order.safety_days) if crop_type else None
    task = _planting_task(db, line)
    has_cycles = bool(active_cycles(db, line.id))
    if order.status != "open" or crop_type is None or to_plant <= 0 or has_cycles or not auto_planting(db, order.id):
        _drop_pending_task(db, line)
        db.flush()
        return
    # A remembered id whose task is gone means the user deleted the activity: respect that.
    if task is None and line.planting_task_id is None:
        task = Activity(kind="order_planting", title="", planned_date=line.latest_sow_date, status="pending", source="auto")
        db.add(task)
    if task is not None and task.status == "pending":
        task.title = f"เพาะกล้า {crop_type.name} {to_plant:g} {line.unit} ตามออเดอร์ {order.order_no}"
        task.planned_date = line.latest_sow_date
        db.flush()
        line.planting_task_id = task.id
    db.flush()


def replan_open_orders(db: Session) -> None:
    """Re-plan every open line after stock, crop cycles, orders or the date changed."""
    db.flush()
    rows = db.execute(
        select(SalesOrder, SalesOrderLine)
        .join(SalesOrderLine, SalesOrderLine.order_id == SalesOrder.id)
        .where(SalesOrder.status == "open")
        .order_by(SalesOrderLine.id)
    ).all()
    if not rows:
        return
    coverage = open_coverage(db)
    for order, line in rows:
        _sync_line_planting(db, order, line, coverage[line.id].to_plant)


def replan_open_orders_job(db: Session) -> int:
    replan_open_orders(db)
    db.commit()
    return 1


def _validate_customer(db: Session, customer_id: int) -> None:
    if get_active(db, Customer, customer_id) is None:
        raise ValueError("Customer is not available")


def _validate_line(db: Session, order_date: date, item) -> tuple[float, str]:
    product = get_active(db, Product, item.product_id)
    if product is None or not product.is_active:
        raise ValueError("Product is not available")
    if item.delivery_date < order_date:
        raise ValueError("Delivery date is before the order date")
    try:
        quantity = Decimal(str(item.quantity)).quantize(_QUANTITY, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("Invalid quantity") from exc
    unit = (item.unit or product.unit).strip()
    if quantity <= 0 or convert_quantity(quantity, unit, product.unit) <= 0:
        raise ValueError("Invalid quantity or unit")
    return float(quantity), unit


def order_lines(db: Session, order_id: int) -> list[SalesOrderLine]:
    return list(db.scalars(
        select(SalesOrderLine).where(SalesOrderLine.order_id == order_id).order_by(SalesOrderLine.id)
    ).all())


def create_order(db: Session, payload, created_by: int | None) -> SalesOrder:
    _validate_customer(db, payload.customer_id)
    order_date = payload.order_date or today_bangkok()
    order = SalesOrder(
        order_no=_next_order_no(db, order_date),
        customer_id=payload.customer_id,
        order_date=order_date,
        safety_days=payload.safety_days,
        delivery_location_encrypted=_encrypt(payload.delivery_location),
        note_encrypted=_encrypt(payload.note),
        status="open",
        created_by=created_by,
    )
    db.add(order)
    db.flush()
    _set_auto_planting(db, order.id, payload.auto_planting)
    for item in payload.lines:
        quantity, unit = _validate_line(db, order_date, item)
        line = SalesOrderLine(
            order_id=order.id, product_id=item.product_id, quantity=quantity, unit=unit,
            delivery_date=item.delivery_date,
        )
        db.add(line)
        db.flush()
        _set_line_price(db, line.id, item.unit_price)
    replan_open_orders(db)
    return order


def update_order(db: Session, order: SalesOrder, payload) -> None:
    if order.status != "open":
        raise OrderConflict("Order is closed")
    changes = payload.model_dump(exclude_unset=True, exclude={"lines"})
    if changes.get("customer_id") is not None:
        _validate_customer(db, changes["customer_id"])
        order.customer_id = changes["customer_id"]
    if changes.get("safety_days") is not None:
        order.safety_days = changes["safety_days"]
    if "delivery_location" in changes:
        order.delivery_location_encrypted = _encrypt(changes["delivery_location"])
    if "note" in changes:
        order.note_encrypted = _encrypt(changes["note"])
    if payload.auto_planting is not None:
        _set_auto_planting(db, order.id, payload.auto_planting)
    if payload.lines is not None:
        _replace_lines(db, order, payload.lines)
        for line in order_lines(db, order.id):
            if line.planting_task_id is not None and _planting_task(db, line) is None:
                line.planting_task_id = None
    replan_open_orders(db)


def _replace_lines(db: Session, order: SalesOrder, items) -> None:
    existing = {line.id: line for line in order_lines(db, order.id)}
    kept: set[int] = set()
    for item in items:
        quantity, unit = _validate_line(db, order.order_date, item)
        if item.id is None:
            line = SalesOrderLine(order_id=order.id)
            db.add(line)
        else:
            line = existing.get(item.id)
            if line is None or item.id in kept:
                raise ValueError("Order line is not available")
            kept.add(item.id)
            delivered = delivered_quantity(db, line.id)
            if delivered and (quantity < delivered or unit != line.unit):
                raise OrderConflict("Order line already has deliveries")
            if line.product_id != item.product_id:
                if delivered or active_cycles(db, line.id):
                    raise OrderConflict("Order line already has crop cycles")
                _drop_pending_task(db, line)
                line.planting_task_id = None
                _set_line_price(db, line.id, None)
        line.product_id = item.product_id
        line.quantity = quantity
        line.unit = unit
        line.delivery_date = item.delivery_date
        db.flush()
        # A user who cannot see the price leaves the field out, which keeps it.
        if "unit_price" in item.model_fields_set:
            _set_line_price(db, line.id, item.unit_price)
    for line_id, line in existing.items():
        if line_id in kept:
            continue
        # Links to removed (soft-deleted) cycles are history too, so keep the line.
        if db.scalar(select(SalesOrderCycle.id).where(SalesOrderCycle.line_id == line_id).limit(1)):
            raise OrderConflict("Order line already has crop cycles")
        if db.scalar(select(SalesOrderDelivery.id).where(SalesOrderDelivery.line_id == line_id).limit(1)):
            raise OrderConflict("Order line already has deliveries")
        _drop_pending_task(db, line)
        _set_line_price(db, line.id, None)
        db.delete(line)
    db.flush()


def close_order(db: Session, order: SalesOrder, status: str) -> None:
    if order.status != "open":
        raise OrderConflict("Order is closed")
    order.status = status
    order.closed_at = utc_now()
    for line in order_lines(db, order.id):
        _sync_line_planting(db, order, line, 0)
    replan_open_orders(db)


def deliver_order(db: Session, order: SalesOrder, payload, created_by: int | None):
    """Post one outbound document for the delivered lines and close the order when complete."""
    if order.status != "open":
        raise OrderConflict("Order is closed")
    lines = {line.id: line for line in order_lines(db, order.id)}
    document_lines, quantities = [], []
    for item in payload.lines:
        line = lines.pop(item.line_id, None)
        if line is None:
            raise ValueError("Order line is not available")
        quantity = item.quantity.quantize(_QUANTITY, rounding=ROUND_HALF_UP)
        left = Decimal(str(line.quantity)) - Decimal(str(delivered_quantity(db, line.id)))
        if quantity <= 0:
            raise ValueError("Invalid quantity")
        if quantity > left.quantize(_QUANTITY, rounding=ROUND_HALF_UP):
            raise OrderConflict("Delivery is more than the outstanding quantity")
        price = item.unit_price
        if price is None and item.use_order_price:
            price = _agreed_price(db, line.id)
        document_lines.append({
            "product_id": line.product_id, "quantity": quantity, "unit": line.unit, "unit_price": price,
        })
        quantities.append((line.id, quantity))
    document, warnings = create_stock_document(db, "outbound", OutboundDocumentCreate(
        doc_date=payload.doc_date, customer_id=order.customer_id, reference_no=order.order_no, note=payload.note,
        lines=document_lines,
    ), created_by)
    set_document_purpose(db, document.id, "order", order.id)
    if payload.record_finance:
        create_auto_finance_for_document(db, document, created_by)
    for line_id, quantity in quantities:
        db.add(SalesOrderDelivery(line_id=line_id, document_id=document.id, quantity=float(quantity)))
    db.flush()
    if payload.close_when_complete and all(delivered_quantity(db, line.id) >= line.quantity for line in order_lines(db, order.id)):
        close_order(db, order, "delivered")
    else:
        replan_open_orders(db)
    return document, warnings


def reopen_for_voided_document(db: Session, document_id: int) -> None:
    """A voided delivery is outstanding again, so its order must be open."""
    orders = db.scalars(
        select(SalesOrder)
        .join(SalesOrderLine, SalesOrderLine.order_id == SalesOrder.id)
        .join(SalesOrderDelivery, SalesOrderDelivery.line_id == SalesOrderLine.id)
        .where(SalesOrderDelivery.document_id == document_id, SalesOrder.status == "delivered")
        .distinct()
    ).all()
    for order in orders:
        order.status = "open"
        order.closed_at = None


def _kilograms(quantity: float, unit: str) -> float | None:
    try:
        return convert_quantity(quantity, unit, "kg")
    except ValueError:
        return None


def plants_needed(db: Session, quantity: float, unit: str, crop_type: CropType) -> int | None:
    """Plants to sow from past yield per plant; None without that history or a mass unit."""
    per_plant = average_yield_per_plant_kg(db, crop_type.id)
    kilograms = _kilograms(quantity, unit) if quantity > 0 else None
    if not per_plant or kilograms is None:
        return None
    return max(1, math.ceil(round(kilograms / per_plant, 6)))


def tables_needed(db: Session, quantity: float, unit: str, crop_type: CropType) -> int | None:
    """Tables to plant: by plants and free room when yield per plant is known, else by past cycles."""
    plants = plants_needed(db, quantity, unit, crop_type)
    if plants is not None:
        count = 0
        for space in free_table_spaces(db):
            if plants <= 0:
                break
            plants -= space.free
            count += 1
        return count + (math.ceil(plants / DEFAULT_TABLE_CAPACITY) if plants > 0 else 0)
    average = average_yield_kg(db, crop_type.id)
    kilograms = _kilograms(quantity, unit) if quantity > 0 else None
    if not average or kilograms is None:
        return None
    return max(1, math.ceil(round(kilograms / average, 6)))


def free_tables(db: Session) -> list[Table]:
    """Tables with room for more plants; a harvested table is free only once it is cleaned."""
    return [space.table for space in free_table_spaces(db)]


def _batch_for(db: Session, sow_date: date) -> Batch | None:
    started = db.scalar(
        select(Batch).where(Batch.start_date <= sow_date).order_by(Batch.start_date.desc(), Batch.id).limit(1)
    )
    return started or db.scalar(select(Batch).order_by(Batch.start_date, Batch.id).limit(1))


def planting_ready(db: Session, order: SalesOrder, line: SalesOrderLine) -> bool:
    task = _planting_task(db, line)
    return (
        order.status == "open"
        and (not auto_planting(db, order.id) or (task is not None and task.status == "done"))
        and _crop_type_for(db, line.product_id) is not None
        and not active_cycles(db, line.id)
    )


def planting_flags_for_tasks(db: Session, task_ids: list[int]) -> dict[int, tuple[int, bool]]:
    if not task_ids:
        return {}
    rows = db.execute(
        select(SalesOrder, SalesOrderLine)
        .join(SalesOrderLine, SalesOrderLine.order_id == SalesOrder.id)
        .where(SalesOrderLine.planting_task_id.in_(task_ids))
    ).all()
    return {line.planting_task_id: (line.id, planting_ready(db, order, line)) for order, line in rows}


def planting_proposal(db: Session, order: SalesOrder, line: SalesOrderLine) -> dict:
    crop_type = _crop_type_for(db, line.product_id)
    if crop_type is None:
        raise ValueError("Product is not mapped to a crop type")
    sow_date = today_bangkok()
    to_plant = open_coverage(db).get(line.id, Coverage()).to_plant
    needed = tables_needed(db, to_plant, line.unit, crop_type)
    plants = plants_needed(db, to_plant, line.unit, crop_type)
    spaces = free_table_spaces(db)
    available = [{"id": space.table.id, "table_number": space.table.table_number,
                  "capacity_plants": space.capacity, "free_plants": space.free} for space in spaces]
    ready_date = sow_date + timedelta(days=crop_type.nursery_days + crop_type.growth_days)
    return {
        "line_id": line.id,
        "order_no": order.order_no,
        "crop_name": crop_type.name,
        "quantity": line.quantity,
        "unit": line.unit,
        "to_plant": to_plant,
        "delivery_date": line.delivery_date,
        "nursery_start": sow_date,
        "expected_ready_date": ready_date,
        "is_late": ready_date + timedelta(days=order.safety_days) > line.delivery_date,
        "tables_needed": needed,
        "plants_needed": plants,
        "free_tables": available,
        "suggested_table_ids": [table["id"] for table in available[: needed or 1]],
        "can_create": planting_ready(db, order, line),
    }


def create_cycles_for_line(
    db: Session, order: SalesOrder, line: SalesOrderLine, table_ids: list[int], nursery_start: date,
    create_tasks: bool = True,
) -> list[CropCycle]:
    crop_type = _crop_type_for(db, line.product_id)
    if crop_type is None:
        raise ValueError("Product is not mapped to a crop type")
    if not planting_ready(db, order, line):
        raise OrderConflict("Planting task is not completed or crop cycles already exist")
    if len(set(table_ids)) != len(table_ids):
        raise ValueError("Duplicate table")
    room = {space.table.id: space.free for space in free_table_spaces(db)}
    if not set(table_ids) <= set(room):
        raise OrderConflict("A selected table is not free")
    to_plant = open_coverage(db).get(line.id, Coverage()).to_plant
    plants_left = plants_needed(db, to_plant, line.unit, crop_type)
    batch = _batch_for(db, nursery_start)
    if batch is None:
        raise ValueError("No batch is available")
    cycles = []
    for table_id in table_ids:
        # With a known yield per plant, fill each table's free room until the order is covered.
        plant_count = None
        if plants_left is not None:
            plant_count = max(0, min(room[table_id], plants_left))
            plants_left -= plant_count
        cycle = CropCycle(
            table_id=table_id, batch_id=batch.id, crop_type_id=crop_type.id,
            nursery_start=nursery_start, status=CycleStatus.nursery, plant_count=plant_count or None,
        )
        db.add(cycle)
        db.flush()
        save_cycle_options(db, cycle.id, {"create_tasks": create_tasks})
        start_cycle(db, cycle)
        db.add(SalesOrderCycle(line_id=line.id, cycle_id=cycle.id))
        cycles.append(cycle)
    replan_open_orders(db)
    return cycles


def _planting_status(
    product: Product, crop_type, cycles, task, line: SalesOrderLine, cover: Coverage, automatic: bool
) -> str:
    if cover.delivered >= line.quantity:
        return "delivered"
    if crop_type is None:
        return "unmapped" if product.category == "vegetable" else "not_required"
    if cycles:
        return "planted"
    if task is not None and task.status == "done":
        return "ready"
    if cover.to_plant <= 0:
        return "covered"
    if not automatic:
        return "manual"
    if line.latest_sow_date and line.latest_sow_date < today_bangkok():
        return "late"
    return "waiting"


def present_orders(db: Session, orders: list[SalesOrder], role) -> list[dict]:
    coverage = open_coverage(db)
    return [_present_order(db, order, role, coverage) for order in orders]


def present_order(db: Session, order: SalesOrder, role) -> dict:
    return present_orders(db, [order], role)[0]


def _present_order(db: Session, order: SalesOrder, role, coverage: dict[int, Coverage]) -> dict:
    customer = db.get(Customer, order.customer_id)
    name = present_text_safe(customer.name_encrypted, role, table="customers", row_id=customer.id, field="name")
    location = present_text_safe(
        order.delivery_location_encrypted, role, table="sales_orders", row_id=order.id, field="delivery_location"
    )
    note = present_text_safe(order.note_encrypted, role, table="sales_orders", row_id=order.id, field="note")
    failed = name.decrypt_failed or any(
        result.decrypt_failed
        for token, result in ((order.delivery_location_encrypted, location), (order.note_encrypted, note))
        if token
    )
    lines = []
    automatic = auto_planting(db, order.id)
    for line in order_lines(db, order.id):
        price_row = _line_price(db, line.id)
        price = present_number_safe(
            price_row.unit_price_encrypted if price_row else None, role,
            table="sales_order_line_prices", row_id=price_row.id if price_row else 0, field="unit_price",
        )
        failed = failed or price.decrypt_failed
        product = db.get(Product, line.product_id)
        product_name = present_text_safe(
            product.name_encrypted, role, table="products", row_id=product.id, field="name"
        )
        failed = failed or product_name.decrypt_failed
        crop_type = _crop_type_for(db, line.product_id)
        cycles = active_cycles(db, line.id)
        task = _planting_task(db, line)
        cover = coverage.get(line.id) or Coverage(delivered=delivered_quantity(db, line.id))
        lines.append({
            "id": line.id,
            "product_id": line.product_id,
            "product_name": product_name.value,
            "crop_name": crop_type.name if crop_type else None,
            "quantity": line.quantity,
            "unit": line.unit,
            "delivery_date": line.delivery_date,
            "latest_sow_date": line.latest_sow_date,
            "planting_status": _planting_status(product, crop_type, cycles, task, line, cover, automatic),
            "planting_ready": planting_ready(db, order, line),
            "unit_price": price.value,
            "has_price": price_row is not None,
            "delivered_quantity": cover.delivered,
            "from_stock": cover.from_stock,
            "from_growing": cover.from_growing,
            "to_plant": cover.to_plant,
            "planting_task_id": task.id if task else None,
            "tables_needed": tables_needed(db, cover.to_plant, line.unit, crop_type) if crop_type and not cycles else None,
            "cycle_ids": [cycle.id for cycle in cycles],
        })
    return {
        "id": order.id,
        "order_no": order.order_no,
        "customer_id": order.customer_id,
        "customer_name": name.value,
        "order_date": order.order_date,
        "safety_days": order.safety_days,
        "delivery_location": location.value if order.delivery_location_encrypted else None,
        "note": note.value if order.note_encrypted else None,
        "status": order.status,
        "auto_planting": automatic,
        "lines": lines,
        "is_masked": role.value != "owner",
        "decrypt_failed": failed,
        "created_at": order.created_at,
    }
