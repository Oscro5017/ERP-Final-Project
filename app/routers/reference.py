from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Batch, CropCycle, CropType, Product, Table
from ..schemas import BatchResponse, CropTypeProductMappingUpdate, CropTypeResponse, TableResponse
from ..security import get_current_user
from ..services.crop_cycle_stock import sync_crop_cycle_harvest_stock

router = APIRouter(tags=["reference"])


@router.get("/tables", response_model=list[TableResponse])
def list_tables(db: Session = Depends(get_db), _=Depends(get_current_user)):
    return db.scalars(select(Table).order_by(Table.table_number)).all()


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
    db.commit()
    response = CropTypeResponse.model_validate(crop_type)
    response.warnings = sorted(warnings)
    return response
