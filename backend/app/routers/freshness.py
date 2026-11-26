from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import StockWaste, User
from ..schemas import (
    FreshnessOverviewResponse,
    LotExpiryUpdate,
    ShelfLifeResponse,
    ShelfLifeUpdate,
    StockWasteCreate,
    StockWasteListResponse,
    StockWasteResponse,
)
from ..security import get_current_user
from ..services import freshness as service
from ..services.sales_orders import replan_open_orders

router = APIRouter(prefix="/freshness", tags=["freshness"])


def _run(db: Session, operation):
    """Run and commit one change, mapping domain errors to HTTP errors."""
    try:
        result = operation()
        replan_open_orders(db)
        db.commit()
        return result
    except service.FreshnessConflict as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc))
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Stock changed at the same time; please retry")


@router.get("/lots", response_model=FreshnessOverviewResponse)
def list_lots(
    product_id: int | None = Query(default=None, gt=0),
    include_empty: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return service.overview(db, user.role, product_id, include_empty)


@router.put("/products/{product_id}", response_model=ShelfLifeResponse)
def set_shelf_life(
    product_id: int, payload: ShelfLifeUpdate, db: Session = Depends(get_db), _user: User = Depends(get_current_user)
):
    return _run(db, lambda: service.save_setting(db, product_id, payload.shelf_life_days, payload.warn_days))


@router.delete("/products/{product_id}", status_code=204)
def remove_shelf_life(product_id: int, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    setting = service.get_setting(db, product_id)
    if setting is None:
        raise HTTPException(status_code=404, detail="Shelf life is not set")
    db.delete(setting)
    replan_open_orders(db)
    db.commit()
    return Response(status_code=204)


@router.put("/products/{product_id}/lots/{lot_key}/expiry", response_model=FreshnessOverviewResponse)
def set_lot_expiry(
    product_id: int,
    lot_key: str,
    payload: LotExpiryUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _run(db, lambda: service.override_expiry(db, product_id, lot_key, payload.expires_on, payload.reason))
    return service.overview(db, user.role, product_id, False)


@router.get("/waste", response_model=StockWasteListResponse)
def list_waste(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    total = db.scalar(select(func.count()).select_from(StockWaste)) or 0
    rows = db.scalars(select(StockWaste).order_by(StockWaste.id.desc()).offset(offset).limit(limit)).all()
    return {"items": [service.present_waste(db, row, user.role) for row in rows], "total": total}


@router.post("/waste", response_model=StockWasteResponse, status_code=201)
def create_waste(payload: StockWasteCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    waste = _run(db, lambda: service.record_waste(db, payload, user.id))
    return service.present_waste(db, waste, user.role)


@router.post("/waste/{waste_id}/void", response_model=StockWasteResponse)
def void_waste(waste_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    waste = db.get(StockWaste, waste_id)
    if waste is None:
        raise HTTPException(status_code=404, detail="Waste record not found")
    _run(db, lambda: service.void_waste(db, waste))
    return service.present_waste(db, waste, user.role)
