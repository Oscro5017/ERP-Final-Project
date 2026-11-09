from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from ..database import get_db
from ..models import CropCycle, Role, Task, User, utc_now
from ..query_helpers import active_rows, get_active
from ..schemas import TaskCreate, TaskCycleInfo, TaskResponse, TaskUpdate
from ..security import get_current_user
from ..services.secure_fields import encrypt_text, present_text_safe, safe_decrypt_text

router = APIRouter(prefix="/tasks", tags=["tasks"])


def build_task_response(task: Task, role: Role) -> TaskResponse:
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
        table="tasks",
        row_id=task.id,
        field="title",
    )
    title = title_result.value if task.is_encrypted else task.title

    return TaskResponse(
        id=task.id,
        cycle_id=task.cycle_id,
        title=title,
        due_date=task.due_date,
        status=task.status,
        source=task.source,
        created_at=task.created_at,
        cycle_info=cycle_info,
        is_masked=task.is_encrypted and role != Role.owner,
        decrypt_failed=title_result.decrypt_failed,
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
        select(Task)
        .options(
            joinedload(Task.cycle).joinedload(CropCycle.table),
            joinedload(Task.cycle).joinedload(CropCycle.crop_type),
        )
        .order_by(Task.due_date.asc(), Task.id.asc()),
        Task,
    )

    if status and status != "all":
        query = query.where(Task.status == status)

    if from_date:
        query = query.where(Task.due_date >= from_date)

    if to_date:
        query = query.where(Task.due_date <= to_date)

    tasks = db.scalars(query).unique().all()
    responses = [build_task_response(task, user.role) for task in tasks]
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
    task_title = task_data.pop("title")
    is_encrypted = task_data.get("source") == "manual"
    task = Task(
        **task_data,
        title=encrypt_text(task_title) if is_encrypted else task_title,
        is_encrypted=is_encrypted,
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    # Re-query with relations for cycle_info
    task_with_relations = (
        db.scalars(
            active_rows(select(Task)
            .options(
                joinedload(Task.cycle).joinedload(CropCycle.table),
                joinedload(Task.cycle).joinedload(CropCycle.crop_type),
            )
            .where(Task.id == task.id), Task)
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
    task = get_active(db, Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    update_data = payload.model_dump(exclude_unset=True)
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
                table="tasks",
                row_id=task.id,
                field="title",
            )
            if title_result.decrypt_failed:
                raise HTTPException(status_code=409, detail="ไม่สามารถเปลี่ยนประเภทงานได้เนื่องจากข้อมูลเข้ารหัสอ่านไม่ได้")
            task.title = title_result.value
            task.is_encrypted = False

    for field, value in update_data.items():
        if field not in {"title", "source"}:
            setattr(task, field, value)
    task.source = next_source

    db.commit()
    db.refresh(task)

    task_with_relations = (
        db.scalars(
            active_rows(select(Task)
            .options(
                joinedload(Task.cycle).joinedload(CropCycle.table),
                joinedload(Task.cycle).joinedload(CropCycle.crop_type),
            )
            .where(Task.id == task.id), Task)
        )
        .unique()
        .first()
    )
    return build_task_response(task_with_relations or task, user.role)


@router.delete("/{task_id}", status_code=204)
def delete_task(
    task_id: int,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    task = get_active(db, Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    task.deleted_at = utc_now()
    db.commit()
