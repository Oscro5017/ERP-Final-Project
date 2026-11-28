from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Batch, CropCycle, CropType, CycleStatus, Product, Table
from ..schemas import (
    BatchResponse, CropTypeProductMappingUpdate, CropTypeResponse, CropTypeUpdate, TableBoardResponse, TableCycleResponse,
    TableResponse, TableUpdate,
)
from ..security import get_current_user
from ..services.crop_cycle_stock import sync_crop_cycle_harvest_stock
from ..services.activities import today_bangkok
from ..services.crop_production import refresh_expected
from ..services.table_space import table_spaces
from ..services.task_generator import sync_crop_cycle_tasks
from ..services.sales_orders import replan_open_orders

router = APIRouter(tags=["reference"])


@router.get("/tables", response_model=list[TableResponse])
def list_tables(db: Session = Depends(get_db), _=Depends(get_current_user)):
    return db.scalars(select(Table).order_by(Table.table_number)).all()


@router.get("/tables/board", response_model=list[TableBoardResponse])
def table_board(db: Session = Depends(get_db), _=Depends(get_current_user)):
    """Every table: what grows on it, how many plants, its stage, and the room left."""
    today = today_bangkok()
    board = []
    for space in table_spaces(db):
        board.append(TableBoardResponse(
            id=space.table.id,
            table_number=space.table.table_number,
            capacity_plants=space.capacity,
            used_plants=space.used,
            free_plants=space.free,
            state=space.state,
            cycles=[
                TableCycleResponse(
                    id=item.cycle.id,
                    cycle_code=item.cycle.cycle_code,
                    crop_type_id=item.cycle.crop_type_id,
                    crop_name=item.cycle.crop_type.name if item.cycle.crop_type else "",
                    status=item.cycle.status.value if hasattr(item.cycle.status, "value") else item.cycle.status,
                    plants=item.plants,
                    plant_count=item.cycle.plant_count,
                    nursery_start=item.cycle.nursery_start,
                    days_since_sowing=(today - item.cycle.nursery_start).days,
                    expected_ready_on=item.cycle.expected_ready_on,
                    awaiting_cleanup=item.awaiting_cleanup,
                )
                for item in space.cycles
            ],
        ))
    return board


@router.patch("/tables/{table_id}", response_model=TableResponse)
def update_table(table_id: int, payload: TableUpdate, db: Session = Depends(get_db), _=Depends(get_current_user)):
    table = db.get(Table, table_id)
    if table is None:
        raise HTTPException(status_code=404, detail="Table not found")
    table.capacity_plants = payload.capacity_plants
    db.commit()
    return table


@router.get("/batches", response_model=list[BatchResponse])
def list_batches(db: Session = Depends(get_db), _=Depends(get_current_user)):
    return db.scalars(select(Batch).order_by(Batch.batch_number)).all()


@router.get("/crop-types", response_model=list[CropTypeResponse])
def list_crop_types(db: Session = Depends(get_db), _=Depends(get_current_user)):
    return db.scalars(select(CropType).order_by(CropType.id)).all()


@router.patch("/crop-types/{crop_type_id}/product-mapping", response_model=CropTypeResponse)
def update_crop_type_product_mapping(
    crop_type_id: int,
    payload: CropTypeProductMappingUpdate,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    crop_type = db.get(CropType, crop_type_id)
    if crop_type is None:
        raise HTTPException(status_code=404, detail="Crop type not found")
    if payload.product_id is not None:
        product = db.get(Product, payload.product_id)
        if product is None or product.deleted_at is not None or not product.is_active:
            raise HTTPException(status_code=422, detail="Product is not available")
        duplicate = db.scalar(select(CropType.id).where(
            CropType.product_id == payload.product_id,
            CropType.id != crop_type_id,
        ))
        if duplicate is not None:
            raise HTTPException(status_code=409, detail="Product is already mapped to another crop type")
    crop_type.product_id = payload.product_id
    db.flush()
    warnings: set[str] = set()
    cycles = db.scalars(select(CropCycle).where(
        CropCycle.crop_type_id == crop_type_id,
        CropCycle.deleted_at.is_(None),
    ).order_by(CropCycle.id)).all()
    for cycle in cycles:
        warnings.update(sync_crop_cycle_harvest_stock(db, cycle))
    replan_open_orders(db)
    db.commit()
    response = CropTypeResponse.model_validate(crop_type)
    response.warnings = sorted(warnings)
    return response


@router.patch("/crop-types/{crop_type_id}", response_model=CropTypeResponse)
def update_crop_type(
    crop_type_id: int,
    payload: CropTypeUpdate,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """Stage lengths and the seed item; cycles still growing follow the new lengths."""
    crop_type = db.get(CropType, crop_type_id)
    if crop_type is None:
        raise HTTPException(status_code=404, detail="Crop type not found")
    changes = payload.model_dump(exclude_unset=True)
    if changes.get("seed_product_id") is not None:
        product = db.get(Product, changes["seed_product_id"])
        if product is None or product.deleted_at is not None or not product.is_active:
            raise HTTPException(status_code=422, detail="Product is not available")
    for field, value in changes.items():
        if field in {"nursery_days", "growth_days"} and value is None:
            continue
        setattr(crop_type, field, value)
    db.flush()
    if {"nursery_days", "growth_days"} & set(changes):
        growing = db.scalars(select(CropCycle).where(
            CropCycle.crop_type_id == crop_type_id,
            CropCycle.deleted_at.is_(None),
            CropCycle.status.in_((CycleStatus.nursery, CycleStatus.bushed)),
        )).all()
        for cycle in growing:
            refresh_expected(db, cycle, {"crop_type_id"})
            sync_crop_cycle_tasks(db, cycle)
        replan_open_orders(db)
    db.commit()
    return CropTypeResponse.model_validate(crop_type)
