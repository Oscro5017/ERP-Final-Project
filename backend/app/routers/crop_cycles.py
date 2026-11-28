from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from ..database import get_db
from ..models import Activity, ActivityTarget, CropCycle, CropCycleStatusLog, CycleStatus, HarvestEntry, User, utc_now
from ..query_helpers import active_rows, get_active
from ..schemas import (
    ChangeNoteResponse,
    CropCycleCreate,
    CropCycleResponse,
    CropCycleStatusChange,
    CropCycleStatusLogResponse,
    CropCycleUpdate,
    HarvestEntryCreate,
    HarvestEntryResponse,
)
from ..security import get_current_user
from ..services.activities import ActivityError, delete_activity, detach_cycle, sync_activity, today_bangkok
from ..services.change_notes import list_changes, record_changes
from ..services.crop_cycle_options import OPTION_FIELDS, save_cycle_options
from ..services.crop_cycle_stock import active_entries, sync_crop_cycle_harvest_stock
from ..services.crop_production import (
    ENTITY,
    cycle_snapshot,
    log_stage_change,
    record_harvest,
    refresh_expected,
    set_total_harvest,
    start_cycle,
    sync_nursery,
    void_harvest,
)
from ..services.sales_orders import replan_open_orders
from ..services.task_generator import sync_crop_cycle_tasks

router = APIRouter(prefix="/crop-cycles", tags=["crop cycles"])

_NOT_FIELDS = OPTION_FIELDS | {"reason", "deduct_seeds"}


def with_relations(query):
    return query.options(joinedload(CropCycle.table), joinedload(CropCycle.batch), joinedload(CropCycle.crop_type))


def _respond(db: Session, cycle_id: int, warnings: list[str]) -> CropCycleResponse:
    response = CropCycleResponse.model_validate(db.scalar(with_relations(select(CropCycle).where(CropCycle.id == cycle_id))))
    response.warnings = sorted(set(warnings))
    return response


def _cycle(db: Session, cycle_id: int) -> CropCycle:
    cycle = get_active(db, CropCycle, cycle_id)
    if not cycle:
        raise HTTPException(status_code=404, detail="Crop cycle not found")
    return cycle


def _unprocessable(exc: ActivityError) -> HTTPException:
    return HTTPException(status_code=404 if "not found" in str(exc) else 422, detail=str(exc))


@router.get("", response_model=list[CropCycleResponse])
def list_cycles(db: Session = Depends(get_db), _=Depends(get_current_user)):
    query = active_rows(select(CropCycle).order_by(CropCycle.id), CropCycle)
    return db.scalars(with_relations(query)).unique().all()


@router.post("", response_model=CropCycleResponse, status_code=201)
def create_cycle(payload: CropCycleCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    cycle = CropCycle(**payload.model_dump(exclude=_NOT_FIELDS | {"harvest_quantity_kg"}))
    db.add(cycle)
    db.flush()
    save_cycle_options(db, cycle.id, payload.model_dump(include=OPTION_FIELDS))
    try:
        warnings = start_cycle(db, cycle, deduct_seeds=payload.deduct_seeds, user_id=user.id)
        if payload.harvest_quantity_kg:
            set_total_harvest(db, cycle, payload.harvest_quantity_kg, cycle.harvest_date)
            warnings += sync_crop_cycle_harvest_stock(db, cycle)
    except ActivityError as exc:
        db.rollback()
        raise _unprocessable(exc) from exc
    replan_open_orders(db)
    db.commit()
    return _respond(db, cycle.id, warnings)


@router.patch("/{cycle_id}", response_model=CropCycleResponse)
def update_cycle(cycle_id: int, payload: CropCycleUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    cycle = _cycle(db, cycle_id)
    before = cycle_snapshot(cycle)
    previous_status = cycle.status
    changes = payload.model_dump(exclude_unset=True, exclude=_NOT_FIELDS)
    quantity_given = "harvest_quantity_kg" in changes
    quantity = changes.pop("harvest_quantity_kg", None)
    for field, value in changes.items():
        setattr(cycle, field, value)
    db.flush()
    save_cycle_options(db, cycle.id, payload.model_dump(include=OPTION_FIELDS))
    refresh_expected(db, cycle, set(changes))
    warnings: list[str] = []
    try:
        if quantity_given or ("harvest_date" in changes and len(active_entries(db, cycle.id)) == 1):
            set_total_harvest(db, cycle, quantity if quantity_given else cycle.harvest_quantity_kg, cycle.harvest_date)
        if {"nursery_start", "seed_count", "crop_type_id"} & set(changes) or payload.deduct_seeds is not None:
            warnings += sync_nursery(db, cycle, deduct_seeds=payload.deduct_seeds is not False, user_id=user.id)
    except ActivityError as exc:
        db.rollback()
        raise _unprocessable(exc) from exc
    on_date = {
        CycleStatus.bushed: cycle.transplant_date,
        CycleStatus.harvested: cycle.harvest_date,
    }.get(cycle.status, today_bangkok())
    log_stage_change(db, cycle, previous_status, on_date=on_date, user_id=user.id, reason=payload.reason)
    record_changes(db, entity_type=ENTITY, entity_id=cycle.id, before=before, after=cycle_snapshot(cycle),
                   user_id=user.id, reason=payload.reason)
    sync_crop_cycle_tasks(db, cycle)
    warnings += sync_crop_cycle_harvest_stock(db, cycle)
    replan_open_orders(db)
    db.commit()
    return _respond(db, cycle.id, warnings)


@router.post("/{cycle_id}/status", response_model=CropCycleResponse)
def change_cycle_status(
    cycle_id: int, payload: CropCycleStatusChange, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    """Move a cycle to a stage straight from a list, with only what that stage needs."""
    cycle = _cycle(db, cycle_id)
    before = cycle_snapshot(cycle)
    previous = cycle.status
    on_date = payload.on_date or today_bangkok()
    warnings: list[str] = []
    try:
        if payload.status in (CycleStatus.harvesting, CycleStatus.harvested) and payload.quantity_kg:
            _entry, warnings = record_harvest(
                db, cycle, on_date, payload.quantity_kg, final=payload.status == CycleStatus.harvested,
                user_id=user.id, reason=payload.reason,
            )
        elif payload.status == CycleStatus.harvesting:
            raise ActivityError("Starting the harvest needs the first harvested quantity")
        else:
            if payload.status == CycleStatus.bushed:
                cycle.transplant_date = on_date
                if payload.plant_count is not None:
                    cycle.plant_count = payload.plant_count
                refresh_expected(db, cycle, {"transplant_date"})
            if payload.status == CycleStatus.harvested and cycle.harvest_date is None:
                cycle.harvest_date = on_date
            cycle.status = payload.status
            log_stage_change(db, cycle, previous, on_date=on_date, user_id=user.id, reason=payload.reason)
    except ActivityError as exc:
        db.rollback()
        raise _unprocessable(exc) from exc
    record_changes(db, entity_type=ENTITY, entity_id=cycle.id, before=before, after=cycle_snapshot(cycle),
                   user_id=user.id, reason=payload.reason)
    sync_crop_cycle_tasks(db, cycle)
    warnings += sync_crop_cycle_harvest_stock(db, cycle)
    replan_open_orders(db)
    db.commit()
    return _respond(db, cycle.id, warnings)


@router.get("/{cycle_id}/harvests", response_model=list[HarvestEntryResponse])
def list_harvests(cycle_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    _cycle(db, cycle_id)
    return db.scalars(select(HarvestEntry).where(HarvestEntry.crop_cycle_id == cycle_id).order_by(
        HarvestEntry.harvested_on, HarvestEntry.id
    )).all()


@router.post("/{cycle_id}/harvests", response_model=CropCycleResponse, status_code=201)
def add_harvest(cycle_id: int, payload: HarvestEntryCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    cycle = _cycle(db, cycle_id)
    before = cycle_snapshot(cycle)
    try:
        _entry, warnings = record_harvest(
            db, cycle, payload.harvested_on or today_bangkok(), payload.quantity_kg, final=payload.final,
            user_id=user.id, reason=payload.reason,
        )
    except ActivityError as exc:
        db.rollback()
        raise _unprocessable(exc) from exc
    record_changes(db, entity_type=ENTITY, entity_id=cycle.id, before=before, after=cycle_snapshot(cycle), user_id=user.id)
    sync_crop_cycle_tasks(db, cycle)
    replan_open_orders(db)
    db.commit()
    return _respond(db, cycle.id, warnings)


@router.delete("/harvests/{entry_id}", status_code=204)
def remove_harvest(entry_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    entry = db.get(HarvestEntry, entry_id)
    if entry is None or entry.voided_at is not None:
        raise HTTPException(status_code=404, detail="Harvest entry not found")
    cycle = _cycle(db, entry.crop_cycle_id)
    before = cycle_snapshot(cycle)
    void_harvest(db, entry)
    record_changes(db, entity_type=ENTITY, entity_id=cycle.id, before=before, after=cycle_snapshot(cycle), user_id=user.id)
    replan_open_orders(db)
    db.commit()


@router.delete("/{cycle_id}", status_code=204)
def delete_cycle(cycle_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    cycle = _cycle(db, cycle_id)
    cycle.deleted_at = utc_now()
    sync_crop_cycle_harvest_stock(db, cycle)
    covering = select(ActivityTarget.activity_id).where(ActivityTarget.crop_cycle_id == cycle.id)
    for activity in db.scalars(active_rows(select(Activity).where(Activity.id.in_(covering)), Activity)).all():
        # An activity that also covers other cycles stays for them; one left with nothing is removed.
        if detach_cycle(db, activity, cycle.id):
            delete_activity(db, activity, "Crop cycle removed")
        else:
            sync_activity(db, activity)
    replan_open_orders(db)
    db.commit()


@router.get("/{cycle_id}/status-log", response_model=list[CropCycleStatusLogResponse])
def list_cycle_status_log(cycle_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    _cycle(db, cycle_id)
    query = select(CropCycleStatusLog).where(CropCycleStatusLog.cycle_id == cycle_id).order_by(
        CropCycleStatusLog.changed_at, CropCycleStatusLog.id
    )
    return db.scalars(query).all()


@router.get("/{cycle_id}/changes", response_model=list[ChangeNoteResponse])
def list_cycle_changes(cycle_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _cycle(db, cycle_id)
    return [ChangeNoteResponse(**vars(change)) for change in list_changes(db, ENTITY, cycle_id, user.role)]

