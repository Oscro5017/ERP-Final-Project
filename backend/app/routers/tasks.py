from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from ..database import get_db
from ..models import CropCycle, Role, Activity, User, utc_now
from ..query_helpers import active_rows, get_active
from ..schemas import TaskCreate, TaskCycleInfo, TaskResponse, TaskUpdate
from ..security import get_current_user
from ..services.secure_fields import encrypt_number, encrypt_text, present_number_safe, present_text_safe, safe_decrypt_text
from ..services.sales_orders import planting_flags_for_tasks
from ..services.task_finance import sync_task_finance, void_task_finance

router = APIRouter(prefix="/tasks", tags=["tasks"])


def build_task_response(task: Activity, role: Role, planting: tuple[int, bool] | None = None) -> TaskResponse:
    cycle_info = None
    if task.cycle:
        table_num = task.cycle.table.table_number if task.cycle.table else None
        crop_name = task.cycle.crop_type.name if task.cycle.crop_type else None
        cycle_info = TaskCycleInfo(
            id=task.cycle.id,
            cycle_code=task.cycle.cycle_code,
            table_number=table_num,
            crop_name=crop_name,
        )

    title_result = present_text_safe(
        task.title if task.is_encrypted else None,
        role,
        table="activities",
        row_id=task.id,
        field="title",
    )
    title = title_result.value if task.is_encrypted else task.title
    labor_result = present_number_safe(task.labor_cost_encrypted, role, table="activities", row_id=task.id, field="labor_cost")
    extra_result = present_number_safe(task.extra_cost_encrypted, role, table="activities", row_id=task.id, field="extra_cost")

    return TaskResponse(
        id=task.id,
        cycle_id=task.cycle_id,
        title=title,
        due_date=task.planned_date,
        status=task.status,
        source=task.source,
        labor_cost=labor_result.value,
        worker_count=task.worker_count,
        extra_cost=extra_result.value,
        created_at=task.created_at,
        cycle_info=cycle_info,
        order_line_id=planting[0] if planting else None,
        planting_ready=planting[1] if planting else False,
        is_masked=(task.is_encrypted or task.labor_cost_encrypted is not None or task.extra_cost_encrypted is not None) and role != Role.owner,
        decrypt_failed=title_result.decrypt_failed or labor_result.decrypt_failed or extra_result.decrypt_failed,
    )


@router.get("", response_model=list[TaskResponse])
def list_tasks(
    status: str | None = Query(None),
    from_date: date | None = Query(None, alias="from"),
    to_date: date | None = Query(None, alias="to"),
    q: str | None = Query(None, max_length=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if q and user.role != Role.owner:
        raise HTTPException(status_code=403, detail="Task search is available to the owner only")
    query = active_rows(
        select(Activity)
        .options(
            joinedload(Activity.cycle).joinedload(CropCycle.table),
            joinedload(Activity.cycle).joinedload(CropCycle.crop_type),
        )
        .order_by(Activity.planned_date.asc(), Activity.id.asc()),
        Activity,
    )

    if status and status != "all":
        query = query.where(Activity.status == status)

    if from_date:
        query = query.where(Activity.planned_date >= from_date)

    if to_date:
        query = query.where(Activity.planned_date <= to_date)

    tasks = db.scalars(query).unique().all()
    planting = planting_flags_for_tasks(db, [task.id for task in tasks])
    responses = [build_task_response(task, user.role, planting.get(task.id)) for task in tasks]
    if q:
        normalized_query = q.casefold().strip()
        responses = [
            response
            for response in responses
            if normalized_query in " ".join((
                response.title,
                response.cycle_info.cycle_code if response.cycle_info else "",
                str(response.cycle_info.table_number or "") if response.cycle_info else "",
                response.cycle_info.crop_name or "" if response.cycle_info else "",
            )).casefold()
        ]
    return responses


@router.post("", response_model=TaskResponse, status_code=201)
def create_task(
    payload: TaskCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if payload.cycle_id:
        cycle = get_active(db, CropCycle, payload.cycle_id)
        if not cycle:
            raise HTTPException(status_code=404, detail="Crop cycle not found")

    task_data = payload.model_dump()
    task_data["planned_date"] = task_data.pop("due_date")
    task_title = task_data.pop("title")
    labor_cost = task_data.pop("labor_cost")
    extra_cost = task_data.pop("extra_cost")
    is_encrypted = task_data.get("source") == "manual"
    task = Activity(
        **task_data,
        title=encrypt_text(task_title) if is_encrypted else task_title,
        is_encrypted=is_encrypted,
        labor_cost_encrypted=encrypt_number(labor_cost).encode("ascii") if labor_cost is not None else None,
        extra_cost_encrypted=encrypt_number(extra_cost).encode("ascii") if extra_cost is not None else None,
    )
    db.add(task)
    db.flush()
    sync_task_finance(db, task, user.id)
    db.commit()
    db.refresh(task)

    # Re-query with relations for cycle_info
    task_with_relations = (
        db.scalars(
            active_rows(select(Activity)
            .options(
                joinedload(Activity.cycle).joinedload(CropCycle.table),
                joinedload(Activity.cycle).joinedload(CropCycle.crop_type),
            )
            .where(Activity.id == task.id), Activity)
        )
        .unique()
        .first()
    )
    return build_task_response(task_with_relations or task, user.role)


@router.patch("/{task_id}", response_model=TaskResponse)
def update_task(
    task_id: int,
    payload: TaskUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    task = get_active(db, Activity, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    update_data = payload.model_dump(exclude_unset=True)
    finance_fields_changed = bool({"status", "cycle_id", "due_date", "labor_cost", "worker_count", "extra_cost"} & set(update_data))
    if "cycle_id" in update_data and update_data["cycle_id"] is not None:
        cycle = get_active(db, CropCycle, update_data["cycle_id"])
        if not cycle:
            raise HTTPException(status_code=404, detail="Crop cycle not found")

    next_source = update_data.get("source", task.source)
    next_title = update_data.get("title")
    if next_title is not None:
        task.title = encrypt_text(next_title) if next_source == "manual" else next_title
        task.is_encrypted = next_source == "manual"
    elif next_source != task.source:
        if next_source == "manual" and not task.is_encrypted:
            task.title = encrypt_text(task.title)
            task.is_encrypted = True
        elif next_source == "auto" and task.is_encrypted:
            title_result = safe_decrypt_text(
                task.title,
                table="activities",
                row_id=task.id,
                field="title",
            )
            if title_result.decrypt_failed:
                raise HTTPException(status_code=409, detail="ไม่สามารถเปลี่ยนประเภทงานได้เนื่องจากข้อมูลเข้ารหัสอ่านไม่ได้")
            task.title = title_result.value
            task.is_encrypted = False

    for field, value in update_data.items():
        if field in {"labor_cost", "extra_cost"}:
            token_field = "labor_cost_encrypted" if field == "labor_cost" else "extra_cost_encrypted"
            setattr(task, token_field, encrypt_number(value).encode("ascii") if value is not None else None)
        elif field == "due_date":
            task.planned_date = value
        elif field not in {"title", "source"}:
            setattr(task, field, value)
    task.source = next_source

    if finance_fields_changed:
        sync_task_finance(db, task, user.id)
    db.commit()
    db.refresh(task)

    task_with_relations = (
        db.scalars(
            active_rows(select(Activity)
            .options(
                joinedload(Activity.cycle).joinedload(CropCycle.table),
                joinedload(Activity.cycle).joinedload(CropCycle.crop_type),
            )
            .where(Activity.id == task.id), Activity)
        )
        .unique()
        .first()
    )
    planting = planting_flags_for_tasks(db, [task.id]).get(task.id)
    return build_task_response(task_with_relations or task, user.role, planting)


@router.delete("/{task_id}", status_code=204)
def delete_task(
    task_id: int,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    task = get_active(db, Activity, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    task.deleted_at = utc_now()
    void_task_finance(db, task.id)
    db.commit()
