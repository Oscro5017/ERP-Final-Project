from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from ..models import Activity, ActivityTarget, CropCycle, Role, Table, User
from ..query_helpers import active_rows
from ..schemas import (
    ActivityCreate,
    ActivityResponse,
    ActivityStatusChange,
    ActivityUpdate,
    ChangeNoteResponse,
    InputCatalogSuggestionResponse,
    InputCatalogSuggestionsResponse,
)
from ..security import get_current_user
from ..services.activities import (
    EDITABLE_KINDS,
    ActivityError,
    ItemInput,
    apply_status,
    default_title,
    delete_activity,
    set_items,
    set_targets,
    sync_activity,
    today_bangkok,
)
from ..services.change_notes import as_text, list_changes, record_changes
from ..services.input_catalog import suggest_input_catalog_with_status
from ..services.sales_orders import planting_flags_for_tasks
from ..services.secure_fields import (
    encrypt_number,
    encrypt_text,
    present_number_safe,
    present_text_safe,
    safe_decrypt_number,
    safe_decrypt_text,
)

router = APIRouter(tags=["activities"])

_TABLE = "activities"
_ENTITY = "activity"


def _load(db: Session, activity_id: int) -> Activity | None:
    statement = active_rows(select(Activity).where(Activity.id == activity_id), Activity).options(
        selectinload(Activity.targets), selectinload(Activity.items)
    )
    return db.scalar(statement)


def _error(exc: ActivityError) -> HTTPException:
    message = str(exc)
    return HTTPException(status_code=404 if "not found" in message else 422, detail=message)


def _token(value) -> bytes | None:
    return encrypt_number(value).encode("ascii") if value is not None else None


def _note_token(note: str | None) -> bytes | None:
    note = (note or "").strip()
    return encrypt_text(note).encode("ascii") if note else None


def _items(payload_items) -> list[ItemInput]:
    return [
        ItemInput(
            item_name=item.item_name,
            quantity=item.quantity,
            unit=item.unit,
            product_id=item.product_id,
            product_id_given="product_id" in item.model_fields_set,
        )
        for item in payload_items
    ]


def _title_text(activity: Activity) -> str:
    if not activity.is_encrypted:
        return activity.title
    return safe_decrypt_text(activity.title, table=_TABLE, row_id=activity.id or 0, field="title").value


def _snapshot(activity: Activity) -> dict:
    """Plain values of everything a change note may describe."""
    items = []
    for item in activity.items:
        name = safe_decrypt_text(item.item_name_encrypted, table="activity_items", row_id=item.id or 0, field="item_name").value
        quantity = safe_decrypt_number(item.quantity_encrypted, table="activity_items", row_id=item.id or 0, field="quantity").value
        items.append(f"{name} {as_text(quantity)} {item.unit}".strip())
    targets = sorted(
        f"cycle:{target.crop_cycle_id}" if target.crop_cycle_id else f"table:{target.table_id}"
        for target in activity.targets
    )
    note = safe_decrypt_text(activity.note_encrypted, table=_TABLE, row_id=activity.id, field="note").value if activity.note_encrypted else None
    cost = {}
    for name in ("labor_cost", "extra_cost"):
        token = getattr(activity, f"{name}_encrypted")
        cost[name] = safe_decrypt_number(token, table=_TABLE, row_id=activity.id, field=name).value if token else None
    return {
        "title": _title_text(activity),
        "status": activity.status,
        "planned_date": activity.planned_date,
        "started_on": activity.started_on,
        "done_on": activity.done_on,
        "targets": ", ".join(targets) or None,
        "items": "; ".join(items) or None,
        "note": note,
        "remind": activity.remind,
        "worker_count": activity.worker_count,
        **cost,
    }


def present_activity(
    db: Session,
    activity: Activity,
    role: Role,
    planting: tuple[int, bool] | None = None,
    warnings: list[str] | None = None,
) -> ActivityResponse:
    is_masked = role != Role.owner
    failed = False
    title = activity.title
    if activity.is_encrypted:
        result = present_text_safe(activity.title, role, table=_TABLE, row_id=activity.id, field="title")
        title, failed = result.value, result.decrypt_failed
    note = present_text_safe(activity.note_encrypted, role, table=_TABLE, row_id=activity.id, field="note")
    labor = present_number_safe(activity.labor_cost_encrypted, role, table=_TABLE, row_id=activity.id, field="labor_cost")
    extra = present_number_safe(activity.extra_cost_encrypted, role, table=_TABLE, row_id=activity.id, field="extra_cost")
    failed = failed or note.decrypt_failed or labor.decrypt_failed or extra.decrypt_failed

    targets = []
    for target in sorted(activity.targets, key=lambda row: (row.crop_cycle_id is None, row.crop_cycle_id or 0, row.table_id or 0)):
        cycle = db.get(CropCycle, target.crop_cycle_id) if target.crop_cycle_id else None
        table = cycle.table if cycle else None
        if table is None and target.table_id is not None:
            table = db.get(Table, target.table_id)
        targets.append({
            "crop_cycle_id": target.crop_cycle_id,
            "table_id": target.table_id,
            "table_number": table.table_number if table else None,
            "cycle_code": cycle.cycle_code if cycle else None,
            "crop_name": cycle.crop_type.name if cycle and cycle.crop_type else None,
            "share": target.share,
            "share_is_manual": target.share_is_manual,
        })

    items = []
    for item in activity.items:
        name = present_text_safe(item.item_name_encrypted, role, table="activity_items", row_id=item.id, field="item_name")
        quantity = present_number_safe(item.quantity_encrypted, role, table="activity_items", row_id=item.id, field="quantity")
        failed = failed or name.decrypt_failed or quantity.decrypt_failed
        items.append({
            "id": item.id,
            "item_name": name.value,
            "quantity": quantity.value,
            "unit": item.unit,
            "product_id": item.product_id,
            "decrypt_failed": name.decrypt_failed or quantity.decrypt_failed,
        })

    return ActivityResponse(
        id=activity.id,
        kind=activity.kind,
        title=title,
        status=activity.status,
        source=activity.source,
        planned_date=activity.planned_date,
        started_on=activity.started_on,
        done_on=activity.done_on,
        remind=activity.remind,
        note=note.value if activity.note_encrypted else None,
        labor_cost=labor.value,
        worker_count=activity.worker_count,
        extra_cost=extra.value,
        targets=targets,
        items=items,
        order_line_id=planting[0] if planting else None,
        planting_ready=planting[1] if planting else False,
        stock_alert_product_id=activity.stock_alert_product_id,
        warnings=warnings or [],
        is_masked=is_masked,
        created_at=activity.created_at,
        decrypt_failed=failed,
    )


def _respond(db: Session, activity_id: int, role: Role, warnings: list[str] | None = None) -> ActivityResponse:
    activity = _load(db, activity_id)
    planting = planting_flags_for_tasks(db, [activity_id]).get(activity_id)
    return present_activity(db, activity, role, planting, warnings)


@router.get("/activities", response_model=list[ActivityResponse])
def list_activities(
    kind: str | None = Query(None),
    status: str | None = Query(None),
    from_date: date | None = Query(None, alias="from"),
    to_date: date | None = Query(None, alias="to"),
    cycle_id: int | None = Query(None),
    table_id: int | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    statement = active_rows(select(Activity), Activity).options(
        selectinload(Activity.targets), selectinload(Activity.items)
    ).order_by(Activity.planned_date.asc(), Activity.id.asc())
    if kind:
        statement = statement.where(Activity.kind.in_(kind.split(",")))
    if status and status != "all":
        statement = statement.where(Activity.status.in_(status.split(",")))
    if from_date:
        statement = statement.where(Activity.planned_date >= from_date)
    if to_date:
        statement = statement.where(Activity.planned_date <= to_date)
    if cycle_id is not None:
        statement = statement.where(Activity.id.in_(
            select(ActivityTarget.activity_id).where(ActivityTarget.crop_cycle_id == cycle_id)
        ))
    if table_id is not None:
        statement = statement.where(Activity.id.in_(
            select(ActivityTarget.activity_id).where(ActivityTarget.table_id == table_id)
        ))
    activities = db.scalars(statement).unique().all()
    planting = planting_flags_for_tasks(db, [activity.id for activity in activities])
    return [present_activity(db, activity, user.role, planting.get(activity.id)) for activity in activities]


@router.post("/activities", response_model=ActivityResponse, status_code=201)
def create_activity(payload: ActivityCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if payload.status != "done" and payload.done_on is not None:
        raise HTTPException(status_code=422, detail="Only a finished activity has a finish date")
    planned = payload.planned_date or payload.done_on or today_bangkok()
    title = (payload.title or "").strip() or default_title(payload.kind)
    activity = Activity(
        kind=payload.kind,
        title=encrypt_text(title),
        is_encrypted=True,
        source="manual",
        planned_date=planned,
        remind=payload.remind if payload.remind is not None else payload.status == "pending",
        note_encrypted=_note_token(payload.note),
        labor_cost_encrypted=_token(payload.labor_cost),
        worker_count=payload.worker_count,
        extra_cost_encrypted=_token(payload.extra_cost),
    )
    db.add(activity)
    try:
        set_targets(db, activity, payload.cycle_ids, payload.table_ids, {s.crop_cycle_id: s.share for s in payload.shares})
        set_items(db, activity, _items(payload.items))
        apply_status(activity, payload.status, payload.done_on or (planned if payload.status == "done" else None))
        result = sync_activity(db, activity, user.id)
    except ActivityError as exc:
        db.rollback()
        raise _error(exc) from exc
    db.commit()
    return _respond(db, activity.id, user.role, result.warnings)


@router.get("/activities/{activity_id}", response_model=ActivityResponse)
def get_activity(activity_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if _load(db, activity_id) is None:
        raise HTTPException(status_code=404, detail="Activity not found")
    return _respond(db, activity_id, user.role)


@router.patch("/activities/{activity_id}", response_model=ActivityResponse)
def update_activity(activity_id: int, payload: ActivityUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    activity = _load(db, activity_id)
    if activity is None:
        raise HTTPException(status_code=404, detail="Activity not found")
    changes = payload.model_dump(exclude_unset=True)
    reason = changes.pop("reason", None)
    managed_by_system = activity.kind not in EDITABLE_KINDS
    if managed_by_system and {"title", "cycle_ids", "table_ids", "shares", "items"} & set(changes):
        raise HTTPException(status_code=422, detail="The system manages this activity's title, crop cycles and items")
    if "done_on" in changes and activity.status != "done":
        raise HTTPException(status_code=422, detail="Only a finished activity has a finish date")
    if "title" in changes and not (changes["title"] or "").strip():
        raise HTTPException(status_code=422, detail="The title cannot be empty")

    before = _snapshot(activity)
    try:
        if "title" in changes:
            activity.title = encrypt_text(changes["title"].strip())
            activity.is_encrypted = True
        if "planned_date" in changes and changes["planned_date"] is not None:
            activity.planned_date = changes["planned_date"]
        if changes.get("done_on") is not None:
            apply_status(activity, "done", changes["done_on"])
        if {"cycle_ids", "table_ids", "shares"} & set(changes):
            current_cycles = [t.crop_cycle_id for t in activity.targets if t.crop_cycle_id is not None]
            current_tables = [t.table_id for t in activity.targets if t.crop_cycle_id is None and t.table_id is not None]
            shares = payload.shares if payload.shares is not None else []
            set_targets(
                db,
                activity,
                payload.cycle_ids if payload.cycle_ids is not None else current_cycles,
                payload.table_ids if payload.table_ids is not None else current_tables,
                {s.crop_cycle_id: s.share for s in shares},
            )
        if payload.items is not None:
            set_items(db, activity, _items(payload.items))
        if "note" in changes:
            activity.note_encrypted = _note_token(changes["note"])
        if changes.get("remind") is not None:
            activity.remind = changes["remind"]
        if "labor_cost" in changes:
            activity.labor_cost_encrypted = _token(changes["labor_cost"])
        if "extra_cost" in changes:
            activity.extra_cost_encrypted = _token(changes["extra_cost"])
        if "worker_count" in changes:
            activity.worker_count = changes["worker_count"]
        result = sync_activity(db, activity, user.id)
    except ActivityError as exc:
        db.rollback()
        raise _error(exc) from exc
    record_changes(
        db, entity_type=_ENTITY, entity_id=activity.id,
        before=before, after=_snapshot(activity), user_id=user.id, reason=reason,
    )
    db.commit()
    return _respond(db, activity.id, user.role, result.warnings)


@router.post("/activities/{activity_id}/status", response_model=ActivityResponse)
def change_activity_status(
    activity_id: int, payload: ActivityStatusChange, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    activity = _load(db, activity_id)
    if activity is None:
        raise HTTPException(status_code=404, detail="Activity not found")
    before = _snapshot(activity)
    apply_status(activity, payload.status, payload.on_date)
    result = sync_activity(db, activity, user.id)
    record_changes(
        db, entity_type=_ENTITY, entity_id=activity.id,
        before=before, after=_snapshot(activity), user_id=user.id, reason=payload.reason,
    )
    db.commit()
    return _respond(db, activity.id, user.role, result.warnings)


@router.delete("/activities/{activity_id}", status_code=204)
def remove_activity(activity_id: int, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    activity = _load(db, activity_id)
    if activity is None:
        raise HTTPException(status_code=404, detail="Activity not found")
    delete_activity(db, activity)
    db.commit()


@router.get("/activities/{activity_id}/changes", response_model=list[ChangeNoteResponse])
def list_activity_changes(activity_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if db.get(Activity, activity_id) is None:
        raise HTTPException(status_code=404, detail="Activity not found")
    return [ChangeNoteResponse(**vars(change)) for change in list_changes(db, _ENTITY, activity_id, user.role)]


@router.get("/input-catalog/suggestions", response_model=InputCatalogSuggestionsResponse)
def get_input_catalog_suggestions(
    q: str = Query(default=""),
    limit: int = Query(default=10, ge=1, le=20),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if user.role != Role.owner:
        return JSONResponse(content={"items": [], "is_masked": True})

    items, decrypt_failed = suggest_input_catalog_with_status(db, q, limit=limit)
    response = InputCatalogSuggestionsResponse(
        items=[
            InputCatalogSuggestionResponse(
                id=item.id,
                item_name=item.name,
                last_unit=item.last_unit,
                last_category=item.last_category,
                last_used_at=item.last_used_at,
                use_count=item.use_count,
                product_id=item.product_id,
                decrypt_failed=False,
            )
            for item in items
        ],
        is_masked=False,
        decrypt_failed=decrypt_failed,
    )
    payload = response.model_dump(mode="json")
    if not decrypt_failed:
        payload.pop("decrypt_failed", None)
    return JSONResponse(content=payload)
