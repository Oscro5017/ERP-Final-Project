"""Activities: the one place farm work is recorded, planned or done.

A finished activity drives what follows from it:
- items linked to a stock item leave the stock on the day the work was done;
- labor and other costs become expenses, split across its crop cycles by share.

Editing an activity recomputes both. Deleting it, or moving it back to "not done",
cancels everything it produced.
"""
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Activity, ActivityItem, ActivityKind, ActivityStatus, ActivityTarget, CropCycle, Product, StockMovement, Table, utc_now
from .input_catalog import upsert_input_catalog
from .products_stock import convert_quantity, record_movement, same_moment, start_of_day, void_source_movements
from .secure_fields import decrypt_number, encrypt_number, encrypt_text
from .source_types import ACTIVITY
from .task_finance import sync_task_finance, void_task_finance

_BANGKOK = ZoneInfo("Asia/Bangkok")

STATUSES = tuple(status.value for status in ActivityStatus)
# Kinds the owner records directly; production stages and system reminders have their own flows.
EDITABLE_KINDS = (
    ActivityKind.fertilize.value,
    ActivityKind.spray.value,
    ActivityKind.cleanup.value,
    ActivityKind.general.value,
)
DEFAULT_TITLES = {
    ActivityKind.nursery.value: "เพาะกล้า",
    ActivityKind.transplant.value: "ย้ายปลูก",
    ActivityKind.harvest.value: "เก็บเกี่ยว",
    ActivityKind.fertilize.value: "ใส่ปุ๋ย",
    ActivityKind.spray.value: "ฉีดพ่น",
    ActivityKind.cleanup.value: "ล้างโต๊ะ",
    ActivityKind.general.value: "งานทั่วไป",
    ActivityKind.stock_alert.value: "ของใกล้หมด",
    ActivityKind.order_planting.value: "ปลูกตามออเดอร์",
}


class ActivityError(ValueError):
    """The request names something that does not exist or cannot be used."""


@dataclass
class ItemInput:
    item_name: str
    quantity: Decimal | float
    unit: str = ""
    product_id: int | None = None
    product_id_given: bool = False


@dataclass
class SyncResult:
    warnings: list[str] = field(default_factory=list)


def today_bangkok() -> date:
    return datetime.now(_BANGKOK).date()


def apply_status(activity: Activity, status: str, on_date: date | None = None) -> None:
    """Set the status and the dates that go with it.

    The start date is kept once set; the finish date exists only while the activity is done.
    """
    if status not in STATUSES:
        raise ActivityError("Unknown activity status")
    if status == ActivityStatus.pending.value:
        activity.started_on = None
        activity.done_on = None
    elif status == ActivityStatus.in_progress.value:
        activity.started_on = on_date or activity.started_on or today_bangkok()
        activity.done_on = None
    else:
        activity.done_on = on_date or activity.done_on or today_bangkok()
        if activity.started_on is None or activity.started_on > activity.done_on:
            activity.started_on = activity.done_on
    activity.status = status


# Targets ---------------------------------------------------------------------

def _active_cycle(db: Session, cycle_id: int) -> CropCycle:
    cycle = db.get(CropCycle, cycle_id)
    if cycle is None or cycle.deleted_at is not None:
        raise ActivityError("Crop cycle not found")
    return cycle


def set_targets(
    db: Session,
    activity: Activity,
    cycle_ids: list[int],
    table_ids: list[int] | None = None,
    shares: dict[int, float] | None = None,
) -> None:
    """Replace the crop cycles and tables an activity covers.

    A cycle brings its table along. ``shares`` fixes the share of some cycles;
    the rest is split by plant count.
    """
    shares = shares or {}
    if len(set(cycle_ids)) != len(cycle_ids):
        raise ActivityError("A crop cycle is listed twice")
    cycles = [_active_cycle(db, cycle_id) for cycle_id in cycle_ids]
    if set(shares) - set(cycle_ids):
        raise ActivityError("A share is given for a crop cycle the activity does not cover")
    if any(share <= 0 for share in shares.values()) or sum(shares.values()) > 1 + 1e-9:
        raise ActivityError("Shares must be positive and add up to at most 1")
    covered_tables = {cycle.table_id for cycle in cycles}
    extra_tables = []
    for table_id in dict.fromkeys(table_ids or []):
        if db.get(Table, table_id) is None:
            raise ActivityError("Table not found")
        if table_id not in covered_tables:
            extra_tables.append(table_id)

    wanted = {(cycle.id, cycle.table_id): cycle for cycle in cycles}
    wanted.update({(None, table_id): None for table_id in extra_tables})
    existing = {(target.crop_cycle_id, target.table_id): target for target in activity.targets}
    for key, target in existing.items():
        if key not in wanted:
            activity.targets.remove(target)
    for key in wanted:
        if key not in existing:
            activity.targets.append(ActivityTarget(crop_cycle_id=key[0], table_id=key[1]))
    for target in activity.targets:
        if target.crop_cycle_id in shares:
            target.share = shares[target.crop_cycle_id]
            target.share_is_manual = True
        elif target.crop_cycle_id is not None:
            target.share_is_manual = False
    activity.cycle_id = cycles[0].id if len(cycles) == 1 else None
    recompute_shares(db, activity)


def recompute_shares(db: Session, activity: Activity) -> None:
    """Split what is not fixed by the owner across cycles by plant count, or equally."""
    cycle_targets = [target for target in activity.targets if target.crop_cycle_id is not None]
    for target in activity.targets:
        if target.crop_cycle_id is None:
            target.share = None
    if not cycle_targets:
        return
    manual = [target for target in cycle_targets if target.share_is_manual]
    automatic = [target for target in cycle_targets if not target.share_is_manual]
    left = max(0.0, 1.0 - sum(target.share or 0 for target in manual))
    if not automatic:
        return
    counts = [db.get(CropCycle, target.crop_cycle_id).plant_count for target in automatic]
    if all(count and count > 0 for count in counts):
        weights = [float(count) for count in counts]
    else:
        weights = [1.0] * len(automatic)
    total = sum(weights)
    for target, weight in zip(automatic, weights):
        target.share = round(left * weight / total, 6)


def cycle_ids_of(activity: Activity) -> list[int]:
    return [target.crop_cycle_id for target in activity.targets if target.crop_cycle_id is not None]


def attach_cycle(db: Session, activity: Activity, cycle: CropCycle) -> None:
    """Point a single-cycle activity (such as a stage reminder) at its cycle."""
    set_targets(db, activity, [cycle.id])


def detach_cycle(db: Session, activity: Activity, cycle_id: int) -> bool:
    """Drop a deleted cycle from an activity; return True when nothing is left to cover."""
    remaining = [cid for cid in cycle_ids_of(activity) if cid != cycle_id]
    tables = [target.table_id for target in activity.targets if target.crop_cycle_id is None and target.table_id]
    manual = {
        target.crop_cycle_id: target.share
        for target in activity.targets
        if target.share_is_manual and target.crop_cycle_id in remaining
    }
    set_targets(db, activity, remaining, tables, manual if sum(manual.values()) <= 1 else None)
    return not activity.targets


# Items -----------------------------------------------------------------------

def _validate_product(db: Session, product_id: int | None) -> None:
    if product_id is None:
        return
    product = db.get(Product, product_id)
    if product is None or product.deleted_at is not None or not product.is_active:
        raise ActivityError("Product is not available")


def set_items(db: Session, activity: Activity, items: list[ItemInput]) -> None:
    """Replace what the activity used, remembering names and stock links for next time."""
    activity.items.clear()
    for item in items:
        name = (item.item_name or "").strip()
        if not name:
            continue
        catalog = upsert_input_catalog(db, name, item.unit, activity.kind)
        if item.product_id_given:
            _validate_product(db, item.product_id)
            catalog.product_id = item.product_id
        product_id = item.product_id if item.product_id_given else catalog.product_id
        _validate_product(db, product_id)
        unit = (item.unit or "").strip() or (catalog.last_unit or "")
        activity.items.append(ActivityItem(
            item_name_encrypted=encrypt_text(name).encode("ascii"),
            quantity_encrypted=encrypt_number(item.quantity).encode("ascii"),
            unit=unit,
            product_id=product_id,
        ))


# Syncing what an activity produced --------------------------------------------

def _wanted_movements(db: Session, activity: Activity) -> tuple[list[tuple[int, float, str]], list[str]]:
    if activity.deleted_at is not None or activity.status != ActivityStatus.done.value:
        return [], []
    wanted, warnings = [], []
    for item in activity.items:
        if item.product_id is None:
            continue
        product = db.get(Product, item.product_id)
        if product is None or product.deleted_at is not None:
            continue
        unit = item.unit.strip() or product.unit
        quantity = decrypt_number(item.quantity_encrypted)
        try:
            delta = -convert_quantity(quantity, unit, product.unit)
        except ValueError:
            warnings.append(f"unit_mismatch:{product.id}")
            continue
        if delta >= 0:
            continue
        wanted.append((product.id, delta, unit))
    return wanted, sorted(set(warnings))


def sync_activity_stock(db: Session, activity: Activity) -> list[str]:
    """Keep the stock movements of a finished activity equal to its items."""
    wanted, warnings = _wanted_movements(db, activity)
    occurred_at = start_of_day(activity.done_on) if wanted else None
    current = db.scalars(select(StockMovement).where(
        StockMovement.source_type == ACTIVITY,
        StockMovement.source_id == activity.id,
        StockMovement.voided_at.is_(None),
    ).order_by(StockMovement.id)).all()
    same = (
        len(current) == len(wanted)
        and sorted((m.product_id, m.quantity_delta) for m in current) == sorted((p, d) for p, d, _u in wanted)
        and all(same_moment(m.occurred_at, occurred_at) for m in current)
    )
    if same:
        return warnings
    if current:
        void_source_movements(db, ACTIVITY, activity.id)
    for product_id, delta, _unit in wanted:
        product = db.get(Product, product_id)
        record_movement(
            db, product_id, delta, product.unit, "application",
            source_type=ACTIVITY, source_id=activity.id, occurred_at=occurred_at,
        )
    return warnings


def sync_activity(db: Session, activity: Activity, user_id: int | None = None) -> SyncResult:
    """Bring stock and expenses in line with the activity as it is now."""
    db.flush()
    warnings = sync_activity_stock(db, activity)
    sync_task_finance(db, activity, user_id)
    return SyncResult(warnings=warnings)


def delete_activity(db: Session, activity: Activity, reason: str = "Task removed") -> None:
    activity.deleted_at = utc_now()
    void_source_movements(db, ACTIVITY, activity.id)
    void_task_finance(db, activity.id, reason)


def default_title(kind: str) -> str:
    return DEFAULT_TITLES.get(kind, DEFAULT_TITLES[ActivityKind.general.value])
