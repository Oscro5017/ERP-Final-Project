from datetime import date, timedelta
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Activity, ActivityKind, CropCycle, CropType, CycleStatus, Table
from ..query_helpers import active_rows
from .activities import apply_status, attach_cycle
from .crop_cycle_options import cycle_option


def sync_crop_cycle_tasks(db: Session, cycle: CropCycle) -> None:
    """
    Keep one planned activity for the cycle's next stage:
    - nursery: transplant, due nursery_start + nursery_days
    - bushed: harvest, due transplant_date + growth_days
    - harvested: cleanup of the table, due tomorrow

    A pending activity follows date changes. A finished one is never recreated.
    """
    table = db.get(Table, cycle.table_id)
    crop_type = db.get(CropType, cycle.crop_type_id)
    if not table or not crop_type:
        return

    table_num = table.table_number

    transplant_due = cycle.expected_transplant_on or cycle.nursery_start + timedelta(days=crop_type.nursery_days)
    if cycle.status == CycleStatus.nursery:
        _upsert_stage_task(db, cycle.id, ActivityKind.transplant, f"ย้ายปลูก โต๊ะ {table_num}", transplant_due)

    elif cycle.status in (CycleStatus.bushed, CycleStatus.ready_to_harvest):
        _finish_pending(db, cycle.id, ActivityKind.transplant, cycle.transplant_date)
        due_date = cycle.expected_ready_on or (cycle.transplant_date or transplant_due) + timedelta(days=crop_type.growth_days)
        _upsert_stage_task(db, cycle.id, ActivityKind.harvest, f"เตรียมเก็บเกี่ยว โต๊ะ {table_num}", due_date)

    elif cycle.status == CycleStatus.harvested:
        _finish_pending(db, cycle.id, ActivityKind.transplant, cycle.transplant_date)
        _finish_pending(db, cycle.id, ActivityKind.harvest, cycle.harvest_date)
        due_date = date.today() + timedelta(days=1)
        _upsert_stage_task(db, cycle.id, ActivityKind.cleanup, f"ทำความสะอาดโต๊ะ {table_num}", due_date)


def _stage_activity(db: Session, cycle_id: int, kind: ActivityKind, *statuses: str) -> Activity | None:
    return db.scalar(active_rows(select(Activity).where(
        Activity.cycle_id == cycle_id,
        Activity.kind == kind.value,
        Activity.status.in_(statuses),
    ), Activity))


def _finish_pending(db: Session, cycle_id: int, kind: ActivityKind, on_date: date | None = None) -> None:
    open_activity = _stage_activity(db, cycle_id, kind, "pending", "in_progress")
    if open_activity:
        apply_status(open_activity, "done", on_date)


def _upsert_stage_task(db: Session, cycle_id: int, kind: ActivityKind, title: str, due_date: date) -> None:
    pending_task = _stage_activity(db, cycle_id, kind, "pending")
    if pending_task:
        if pending_task.planned_date != due_date or pending_task.title != title:
            pending_task.planned_date = due_date
            pending_task.title = title
        return

    if _stage_activity(db, cycle_id, kind, "done", "in_progress"):
        return

    if not cycle_option(db, cycle_id, "create_tasks"):
        return

    activity = Activity(
        kind=kind.value,
        title=title,
        planned_date=due_date,
        status="pending",
        source="auto",
        remind=True,
    )
    db.add(activity)
    attach_cycle(db, activity, db.get(CropCycle, cycle_id))
