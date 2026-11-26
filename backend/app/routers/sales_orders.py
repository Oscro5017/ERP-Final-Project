from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import SalesOrder, SalesOrderLine, User
from ..schemas import (
    PlantingCreate,
    PlantingCreateResponse,
    PlantingProposalResponse,
    SalesOrderClose,
    SalesOrderCreate,
    SalesOrderDeliver,
    SalesOrderDeliverResponse,
    SalesOrderListResponse,
    SalesOrderResponse,
    SalesOrderUpdate,
)
from ..security import get_current_user
from ..services import sales_orders as service

router = APIRouter(prefix="/sales-orders", tags=["sales orders"])


def _order(db: Session, order_id: int) -> SalesOrder:
    order = db.get(SalesOrder, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


def _line(db: Session, line_id: int) -> tuple[SalesOrder, SalesOrderLine]:
    line = db.get(SalesOrderLine, line_id)
    if line is None:
        raise HTTPException(status_code=404, detail="Order line not found")
    return _order(db, line.order_id), line


def _run(db: Session, operation):
    """Run and commit one order change, mapping domain errors to HTTP errors."""
    try:
        result = operation()
        db.commit()
        return result
    except service.OrderConflict as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc))
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Order changed at the same time; please retry")


@router.get("", response_model=SalesOrderListResponse)
def list_orders(
    status: str | None = Query(default=None, pattern="^(open|delivered|cancelled)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    statement = select(SalesOrder)
    if status:
        statement = statement.where(SalesOrder.status == status)
    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    orders = db.scalars(statement.order_by(SalesOrder.id.desc()).offset(offset).limit(limit)).all()
    return {"items": service.present_orders(db, list(orders), user.role), "total": total}


@router.post("", response_model=SalesOrderResponse, status_code=201)
def create_order(payload: SalesOrderCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    order = _run(db, lambda: service.create_order(db, payload, user.id))
    return service.present_order(db, order, user.role)


@router.get("/{order_id}", response_model=SalesOrderResponse)
def get_order(order_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return service.present_order(db, _order(db, order_id), user.role)


@router.patch("/{order_id}", response_model=SalesOrderResponse)
def update_order(
    order_id: int, payload: SalesOrderUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    order = _order(db, order_id)
    _run(db, lambda: service.update_order(db, order, payload))
    return service.present_order(db, order, user.role)


@router.post("/{order_id}/close", response_model=SalesOrderResponse)
def close_order(
    order_id: int, payload: SalesOrderClose, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    order = _order(db, order_id)
    _run(db, lambda: service.close_order(db, order, payload.status))
    return service.present_order(db, order, user.role)


@router.post("/{order_id}/deliver", response_model=SalesOrderDeliverResponse, status_code=201)
def deliver_order(
    order_id: int, payload: SalesOrderDeliver, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    order = _order(db, order_id)
    document, warnings = _run(db, lambda: service.deliver_order(db, order, payload, user.id))
    return {
        "order": service.present_order(db, order, user.role),
        "document_id": document.id,
        "doc_no": document.doc_no,
        "warnings": warnings,
    }


@router.get("/lines/{line_id}/planting", response_model=PlantingProposalResponse)
def get_planting(line_id: int, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    order, line = _line(db, line_id)
    return _run(db, lambda: service.planting_proposal(db, order, line))


@router.post("/lines/{line_id}/planting", response_model=PlantingCreateResponse, status_code=201)
def create_planting(
    line_id: int, payload: PlantingCreate, db: Session = Depends(get_db), _user: User = Depends(get_current_user)
):
    order, line = _line(db, line_id)
    cycles = _run(
        db, lambda: service.create_cycles_for_line(
            db, order, line, payload.table_ids, payload.nursery_start, payload.create_tasks
        )
    )
    return {"cycle_ids": [cycle.id for cycle in cycles]}
