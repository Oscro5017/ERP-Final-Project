"""The production stages of a crop cycle and what each stage change records.

Stages: nursery → bushed (transplanted) → ready_to_harvest → harvesting → harvested.
- Starting a cycle records a finished nursery activity that takes its seeds out of stock.
- Expected stage dates come from the crop type and can be moved for one cycle.
- A cycle becomes ready to harvest by itself on its expected date (daily job).
- Harvests are entries; the first one makes the cycle "harvesting", the final one "harvested".
- A stage changed directly, or on another day than expected, leaves a change note.
"""
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    Activity, ActivityKind, ActivityTarget, AutomationPreference, CropCycle, CropCycleStatusLog, CropType, CycleStatus,
    HarvestEntry, Role, User, utc_now,
)
from .activities import (
    ActivityError, ItemInput, apply_status, delete_activity, set_items, set_targets, sync_activity, today_bangkok,
)
from .change_notes import record_change
from .crop_cycle_stock import active_entries, sync_crop_cycle_harvest_stock

ENTITY = "crop_cycle"
STAGE_LABELS = {
    CycleStatus.nursery.value: "อนุบาล",
    CycleStatus.bushed.value: "ลงปลูก",
    CycleStatus.ready_to_harvest.value: "พร้อมเก็บเกี่ยว",
    CycleStatus.harvesting.value: "กำลังเก็บเกี่ยว",
    CycleStatus.harvested.value: "เก็บเกี่ยวแล้ว",
}
SEED_UNIT = "เมล็ด"


def _value(status) -> str:
    return status.value if hasattr(status, "value") else str(status)


# Expected dates ----------------------------------------------------------------

def refresh_expected(db: Session, cycle: CropCycle, changed: set[str] | None = None) -> None:
    """Fill in or follow the computed stage dates; a date the owner set stays put."""
    changed = changed or set()
    crop_type = db.get(CropType, cycle.crop_type_id)
    if crop_type is None:
        return
    if "expected_transplant_on" not in changed and (
        cycle.expected_transplant_on is None or {"nursery_start", "crop_type_id"} & changed
    ):
        cycle.expected_transplant_on = cycle.nursery_start + timedelta(days=crop_type.nursery_days)
    if "expected_ready_on" not in changed and (
        cycle.expected_ready_on is None or {"nursery_start", "transplant_date", "crop_type_id", "expected_transplant_on"} & changed
    ):
        base = cycle.transplant_date or cycle.expected_transplant_on
        cycle.expected_ready_on = base + timedelta(days=crop_type.growth_days)


def timing_note(stage: str, actual: date | None, expected: date | None) -> str | None:
    """'ลงปลูกก่อนวันที่คำนวณ 2 วัน' when a stage starts on another day than computed."""
    if actual is None or expected is None or actual == expected:
        return None
    days = (actual - expected).days
    when = "ก่อน" if days < 0 else "หลัง"
    return f"{STAGE_LABELS.get(stage, stage)}{when}วันที่คำนวณ {abs(days)} วัน"


def _expected_for(cycle: CropCycle, stage: str) -> date | None:
    if stage == CycleStatus.bushed.value:
        return cycle.expected_transplant_on
    if stage == CycleStatus.ready_to_harvest.value:
        return cycle.expected_ready_on
    return None


def log_stage_change(
    db: Session, cycle: CropCycle, previous, *, on_date: date | None = None, user_id: int | None = None,
    reason: str | None = None, by_system: bool = False,
) -> None:
    """Status history plus a change note, with a timing note when the day differs from the computed one."""
    old, new = _value(previous) if previous is not None else None, _value(cycle.status)
    if old == new:
        return
    db.add(CropCycleStatusLog(cycle_id=cycle.id, from_status=old, to_status=new, changed_at=utc_now()))
    notes = [timing_note(new, on_date, _expected_for(cycle, new))]
    if by_system:
        notes.insert(0, "ระบบเปลี่ยนตามวันที่คำนวณ")
    record_change(
        db, entity_type=ENTITY, entity_id=cycle.id, field="status", old=old, new=new,
        user_id=user_id, reason=reason, auto_note=" · ".join(note for note in notes if note) or None,
    )


# Nursery and seeds ---------------------------------------------------------------

def nursery_activity(db: Session, cycle_id: int) -> Activity | None:
    return db.scalar(select(Activity).where(
        Activity.kind == ActivityKind.nursery.value,
        Activity.deleted_at.is_(None),
        Activity.id.in_(select(ActivityTarget.activity_id).where(ActivityTarget.crop_cycle_id == cycle_id)),
    ))


def sync_nursery(db: Session, cycle: CropCycle, deduct_seeds: bool = True, user_id: int | None = None) -> list[str]:
    """Keep the cycle's finished nursery activity, and its seed deduction, in line with the cycle.

    The record exists only while the cycle says how many seeds were sown.
    """
    crop_type = db.get(CropType, cycle.crop_type_id)
    activity = nursery_activity(db, cycle.id)
    if not cycle.seed_count:
        if activity is not None:
            delete_activity(db, activity, "Seed count removed")
        return []
    if activity is None:
        activity = Activity(
            kind=ActivityKind.nursery.value, title=f"เพาะกล้า {crop_type.name if crop_type else ''}".strip(),
            planned_date=cycle.nursery_start, source="auto",
        )
        db.add(activity)
        set_targets(db, activity, [cycle.id])
    activity.planned_date = cycle.nursery_start
    apply_status(activity, "done", cycle.nursery_start)
    seeds = []
    if deduct_seeds and crop_type and crop_type.seed_product_id and cycle.seed_count:
        seeds = [ItemInput(
            item_name=f"เมล็ด{crop_type.name}", quantity=cycle.seed_count, unit=SEED_UNIT,
            product_id=crop_type.seed_product_id, product_id_given=True,
        )]
    try:
        set_items(db, activity, seeds)
    except ActivityError:
        set_items(db, activity, [])
        return ["seed_product_unavailable"]
    return sync_activity(db, activity, user_id).warnings


def start_cycle(db: Session, cycle: CropCycle, deduct_seeds: bool = True, user_id: int | None = None) -> list[str]:
    """A new cycle: computed dates, its first status entry, stage reminders and the nursery record."""
    from .task_generator import sync_crop_cycle_tasks

    refresh_expected(db, cycle)
    db.add(CropCycleStatusLog(cycle_id=cycle.id, from_status=None, to_status=_value(cycle.status), changed_at=utc_now()))
    sync_crop_cycle_tasks(db, cycle)
    return sync_nursery(db, cycle, deduct_seeds=deduct_seeds, user_id=user_id)


# Harvests --------------------------------------------------------------------

def _harvest_activity(db: Session, cycle_id: int) -> Activity | None:
    return db.scalar(select(Activity).where(
        Activity.kind == ActivityKind.harvest.value,
        Activity.deleted_at.is_(None),
        Activity.status.in_(("pending", "in_progress")),
        Activity.id.in_(select(ActivityTarget.activity_id).where(ActivityTarget.crop_cycle_id == cycle_id)),
    ).order_by(Activity.id))


def sync_harvest_totals(db: Session, cycle: CropCycle) -> None:
    db.flush()
    entries = active_entries(db, cycle.id)
    cycle.harvest_quantity_kg = round(sum(entry.quantity_kg for entry in entries), 3) if entries else None
    if entries:
        cycle.harvest_date = entries[-1].harvested_on


def record_harvest(
    db: Session, cycle: CropCycle, harvested_on: date, quantity_kg: float, final: bool = False, user_id: int | None = None,
    reason: str | None = None,
) -> tuple[HarvestEntry, list[str]]:
    """Add one pick; the first makes the cycle 'harvesting', a final one closes the harvest."""
    if _value(cycle.status) == CycleStatus.harvested.value:
        raise ActivityError("The harvest of this cycle is already closed")
    activity = _harvest_activity(db, cycle.id)
    entry = HarvestEntry(
        crop_cycle_id=cycle.id, activity_id=activity.id if activity else None,
        harvested_on=harvested_on, quantity_kg=quantity_kg,
    )
    db.add(entry)
    previous = cycle.status
    cycle.status = CycleStatus.harvested if final else CycleStatus.harvesting
    if activity is not None:
        apply_status(activity, "done" if final else "in_progress", harvested_on)
    sync_harvest_totals(db, cycle)
    log_stage_change(db, cycle, previous, on_date=harvested_on, user_id=user_id, reason=reason)
    return entry, sync_crop_cycle_harvest_stock(db, cycle)


def set_total_harvest(db: Session, cycle: CropCycle, quantity_kg: float | None, on_date: date | None) -> None:
    """The older single-figure harvest: kept as one entry while the cycle has at most one."""
    entries = active_entries(db, cycle.id)
    if len(entries) > 1:
        raise ActivityError("This cycle was harvested several times; edit its harvest entries instead")
    day = on_date or cycle.harvest_date or today_bangkok()
    if not quantity_kg:
        for entry in entries:
            entry.voided_at = utc_now()
    elif entries:
        entries[0].quantity_kg = quantity_kg
        entries[0].harvested_on = day
    else:
        activity = _harvest_activity(db, cycle.id)
        db.add(HarvestEntry(crop_cycle_id=cycle.id, activity_id=activity.id if activity else None,
                            harvested_on=day, quantity_kg=quantity_kg))
    sync_harvest_totals(db, cycle)


def void_harvest(db: Session, entry: HarvestEntry) -> list[str]:
    entry.voided_at = utc_now()
    cycle = db.get(CropCycle, entry.crop_cycle_id)
    sync_harvest_totals(db, cycle)
    return sync_crop_cycle_harvest_stock(db, cycle)


# Automatic stage changes -----------------------------------------------------------

def owner_allows(db: Session, key: str) -> bool:
    """False when an owner chose to do this by hand."""
    return db.scalar(select(AutomationPreference.id).join(User, User.id == AutomationPreference.user_id).where(
        AutomationPreference.key == key, AutomationPreference.mode == "manual", User.role == Role.owner,
    )) is None


def advance_ready_cycles(db: Session, today: date | None = None) -> int:
    """Daily: transplanted cycles reach 'ready to harvest' on their expected date."""
    from .task_generator import sync_crop_cycle_tasks

    if not owner_allows(db, "auto_stage"):
        return 0
    today = today or today_bangkok()
    cycles = db.scalars(select(CropCycle).where(
        CropCycle.deleted_at.is_(None),
        CropCycle.status == CycleStatus.bushed,
        CropCycle.expected_ready_on.is_not(None),
        CropCycle.expected_ready_on <= today,
    )).all()
    for cycle in cycles:
        previous = cycle.status
        cycle.status = CycleStatus.ready_to_harvest
        log_stage_change(db, cycle, previous, on_date=cycle.expected_ready_on, by_system=True)
        sync_crop_cycle_tasks(db, cycle)
    return len(cycles)


def cycle_snapshot(cycle: CropCycle) -> dict:
    return {
        "table_id": cycle.table_id,
        "crop_type_id": cycle.crop_type_id,
        "nursery_start": cycle.nursery_start,
        "transplant_date": cycle.transplant_date,
        "harvest_date": cycle.harvest_date,
        "harvest_quantity_kg": cycle.harvest_quantity_kg,
        "seed_count": cycle.seed_count,
        "plant_count": cycle.plant_count,
        "expected_transplant_on": cycle.expected_transplant_on,
        "expected_ready_on": cycle.expected_ready_on,
    }

