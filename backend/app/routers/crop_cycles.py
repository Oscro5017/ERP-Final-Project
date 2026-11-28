from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from ..database import get_db
from ..models import CropCycle, CropCycleStatusLog, CycleStatus, Activity, utc_now
from ..query_helpers import active_rows, get_active
from ..schemas import CropCycleCreate, CropCycleResponse, CropCycleStatusLogResponse, CropCycleUpdate
from ..security import get_current_user
from ..services.crop_cycle_options import OPTION_FIELDS, save_cycle_options
from ..services.crop_cycle_stock import sync_crop_cycle_harvest_stock
from ..services.crop_cycle_lifecycle import sync_crop_cycle_lifecycle
from ..services.sales_orders import replan_open_orders
from ..services.task_finance import void_task_finance

router = APIRouter(prefix="/crop-cycles", tags=["crop cycles"])


def with_relations(query):
    return query.options(joinedload(CropCycle.table), joinedload(CropCycle.batch), joinedload(CropCycle.crop_type))


@router.get("", response_model=list[CropCycleResponse])
def list_cycles(db: Session = Depends(get_db), _=Depends(get_current_user)):
    query = active_rows(select(CropCycle).order_by(CropCycle.id), CropCycle)
    return db.scalars(with_relations(query)).unique().all()


@router.post("", response_model=CropCycleResponse, status_code=201)
def create_cycle(payload: CropCycleCreate, db: Session = Depends(get_db), _=Depends(get_current_user)):
    cycle = CropCycle(**payload.model_dump(exclude=OPTION_FIELDS))
    db.add(cycle)
    db.flush()
    save_cycle_options(db, cycle.id, payload.model_dump(include=OPTION_FIELDS))
    sync_crop_cycle_lifecycle(db, cycle, created=True)
    warnings = sync_crop_cycle_harvest_stock(db, cycle)
    replan_open_orders(db)
    db.commit()
    response = CropCycleResponse.model_validate(db.scalar(with_relations(select(CropCycle).where(CropCycle.id == cycle.id))))
    response.warnings = warnings
    return response


@router.patch("/{cycle_id}", response_model=CropCycleResponse)
def update_cycle(cycle_id: int, payload: CropCycleUpdate, db: Session = Depends(get_db), _=Depends(get_current_user)):
    cycle = get_active(db, CropCycle, cycle_id)
    if not cycle:
        raise HTTPException(status_code=404, detail="Crop cycle not found")
    previous_status = cycle.status
    for field, value in payload.model_dump(exclude_unset=True, exclude=OPTION_FIELDS).items():
        setattr(cycle, field, value)
    db.flush()
    save_cycle_options(db, cycle.id, payload.model_dump(include=OPTION_FIELDS))
    sync_crop_cycle_lifecycle(db, cycle, previous_status=previous_status)
    warnings = sync_crop_cycle_harvest_stock(db, cycle)
    replan_open_orders(db)
    db.commit()
    response = CropCycleResponse.model_validate(db.scalar(with_relations(select(CropCycle).where(CropCycle.id == cycle.id))))
    response.warnings = warnings
    return response


@router.delete("/{cycle_id}", status_code=204)
def delete_cycle(cycle_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    cycle = get_active(db, CropCycle, cycle_id)
    if not cycle:
        raise HTTPException(status_code=404, detail="Crop cycle not found")
    cycle.deleted_at = utc_now()
    sync_crop_cycle_harvest_stock(db, cycle)
    for task in db.scalars(active_rows(select(Activity).where(Activity.cycle_id == cycle.id), Activity)).all():
        task.deleted_at = cycle.deleted_at
        void_task_finance(db, task.id, "Crop cycle removed")
    replan_open_orders(db)
    db.commit()


@router.get("/{cycle_id}/status-log", response_model=list[CropCycleStatusLogResponse])
def list_cycle_status_log(cycle_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    cycle = get_active(db, CropCycle, cycle_id)
    if not cycle:
        raise HTTPException(status_code=404, detail="Crop cycle not found")
    query = select(CropCycleStatusLog).where(CropCycleStatusLog.cycle_id == cycle_id).order_by(CropCycleStatusLog.changed_at, CropCycleStatusLog.id)
    return db.scalars(query).all()
