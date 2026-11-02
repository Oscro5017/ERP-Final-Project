from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Batch, CropType, Table
from ..schemas import BatchResponse, CropTypeResponse, TableResponse
from ..security import get_current_user

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
