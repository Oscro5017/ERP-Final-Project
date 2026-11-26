from datetime import date, timedelta
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import CropCycle, CropType, CycleStatus, Table, Task
from ..query_helpers import active_rows
from .crop_cycle_options import cycle_option


def sync_crop_cycle_tasks(db: Session, cycle: CropCycle) -> None:
    """
    Auto-generates or updates tasks for a CropCycle based on its lifecycle status:
    - nursery: task "ย้ายปลูก โต๊ะ {table_number}" due at nursery_start + nursery_days
    - bushed: task "เตรียมเก็บเกี่ยว โต๊ะ {table_number}" due at transplant_date + growth_days
    - harvested: task "ทำความสะอาดโต๊ะ {table_number}" due at today + 1
    
    If the task already exists and is pending, updates due_date if changed.
    If the task is already done, does not recreate it.
    """
    table = db.get(Table, cycle.table_id)
    crop_type = db.get(CropType, cycle.crop_type_id)
    if not table or not crop_type:
        return

    table_num = table.table_number

    if cycle.status == CycleStatus.nursery:
        prefix = "ย้ายปลูก"
        title = f"ย้ายปลูก โต๊ะ {table_num}"
        due_date = cycle.nursery_start + timedelta(days=crop_type.nursery_days)
        _upsert_stage_task(db, cycle.id, prefix, title, due_date)

    elif cycle.status == CycleStatus.bushed:
        # If moving to bushed, auto-complete any pending transplant task
        transplant_pending = db.scalar(
            active_rows(select(Task).where(
                Task.cycle_id == cycle.id,
                Task.title.like("ย้ายปลูก%"),
                Task.status == "pending",
            ), Task)
        )
        if transplant_pending:
            transplant_pending.status = "done"

        prefix = "เตรียมเก็บเกี่ยว"
        title = f"เตรียมเก็บเกี่ยว โต๊ะ {table_num}"
        base_date = cycle.transplant_date or (cycle.nursery_start + timedelta(days=crop_type.nursery_days))
        due_date = base_date + timedelta(days=crop_type.growth_days)
        _upsert_stage_task(db, cycle.id, prefix, title, due_date)

    elif cycle.status == CycleStatus.harvested:
        # If moving to harvested, auto-complete any pending harvest prep task
        harvest_pending = db.scalar(
            active_rows(select(Task).where(
                Task.cycle_id == cycle.id,
                Task.title.like("เตรียมเก็บเกี่ยว%"),
                Task.status == "pending",
            ), Task)
        )
        if harvest_pending:
            harvest_pending.status = "done"

        prefix = "ทำความสะอาดโต๊ะ"
        title = f"ทำความสะอาดโต๊ะ {table_num}"
        due_date = date.today() + timedelta(days=1)
        _upsert_stage_task(db, cycle.id, prefix, title, due_date)


def _upsert_stage_task(db: Session, cycle_id: int, prefix: str, title: str, due_date: date) -> None:
    # Check if there is already a pending task for this stage
    pending_task = db.scalar(
        active_rows(select(Task).where(
            Task.cycle_id == cycle_id,
            Task.title.like(f"{prefix}%"),
            Task.status == "pending",
        ), Task)
    )
    if pending_task:
        if pending_task.due_date != due_date or pending_task.title != title:
            pending_task.due_date = due_date
            pending_task.title = title
        return

    # Check if this task was already completed (done)
    done_task = db.scalar(
        active_rows(select(Task).where(
            Task.cycle_id == cycle_id,
            Task.title.like(f"{prefix}%"),
            Task.status == "done",
        ), Task)
    )
    if done_task:
        # Do not recreate completed task
        return

    if not cycle_option(db, cycle_id, "create_tasks"):
        return

    # Create new auto task
    new_task = Task(
        cycle_id=cycle_id,
        title=title,
        due_date=due_date,
        status="pending",
        source="auto",
    )
    db.add(new_task)
