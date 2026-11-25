from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Product, STOCK_MOVEMENT_TYPES, StockMovement, User
from ..schemas import (
    ProductMovementResponse,
    StockBalanceListResponse,
    StockBalanceResponse,
    StockMovementListResponse,
)
from ..security import get_current_user
from ..services.secure_fields import present_text_safe

router = APIRouter(prefix="/stock", tags=["stock"])
_BANGKOK = ZoneInfo("Asia/Bangkok")


def _utc_boundary(day: date, end_of_day: bool) -> datetime:
    local_time = time.max if end_of_day else time.min
    return datetime.combine(day, local_time, tzinfo=_BANGKOK).astimezone(timezone.utc)


def _present_movement(movement: StockMovement, user: User) -> ProductMovementResponse:
    note = present_text_safe(
        movement.note_encrypted,
        user.role,
        table="stock_movements",
        row_id=movement.id,
        field="note",
    )
    return ProductMovementResponse(
        id=movement.id,
        product_id=movement.product_id,
        quantity_delta=movement.quantity_delta,
        movement_type=movement.movement_type,
        source_type=movement.source_type,
        source_id=movement.source_id,
        occurred_at=movement.occurred_at,
        note=note.value if movement.note_encrypted else None,
        voided=movement.voided_at is not None,
        created_at=movement.created_at,
        updated_at=movement.updated_at,
        is_masked=user.role.value != "owner",
        decrypt_failed=note.decrypt_failed,
    )


@router.get("/balances", response_model=StockBalanceListResponse)
def stock_balances(
    product_id: int | None = Query(default=None, gt=0),
    as_of: date | None = None,
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    day = as_of or datetime.now(_BANGKOK).date()
    if product_id is not None and db.scalar(select(Product.id).where(
        Product.id == product_id, Product.deleted_at.is_(None)
    )) is None:
        raise HTTPException(status_code=404, detail="Product not found")
    movement_join = and_(
        StockMovement.product_id == Product.id,
        StockMovement.voided_at.is_(None),
        StockMovement.occurred_at <= _utc_boundary(day, end_of_day=True),
    )
    statement = select(
        Product,
        func.coalesce(func.sum(StockMovement.quantity_delta), 0.0).label("quantity"),
    ).outerjoin(StockMovement, movement_join).where(Product.deleted_at.is_(None))
    if product_id is not None:
        statement = statement.where(Product.id == product_id)
    total_query = select(func.count()).select_from(
        select(Product.id).where(Product.deleted_at.is_(None), *( [Product.id == product_id] if product_id is not None else [] )).subquery()
    )
    total = db.scalar(total_query) or 0
    rows = db.execute(statement.group_by(Product.id).order_by(Product.id).offset(offset).limit(limit)).all()
    items = []
    for product, balance in rows:
        name = present_text_safe(product.name_encrypted, user.role, table="products", row_id=product.id, field="name")
        quantity = round(float(balance or 0), 3)
        items.append(StockBalanceResponse(
            product_id=product.id,
            product_name=name.value,
            unit=product.unit,
            quantity=quantity,
            negative=quantity < 0,
            as_of=day,
            is_masked=user.role.value != "owner",
            decrypt_failed=name.decrypt_failed,
        ))
    return StockBalanceListResponse(items=items, total=total)


@router.get("/movements", response_model=StockMovementListResponse)
def stock_movements(
    product_id: int | None = Query(default=None, gt=0),
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    movement_type: str | None = None,
    source_type: str | None = None,
    source_id: int | None = Query(default=None, gt=0),
    include_void: bool = False,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if movement_type is not None and movement_type not in STOCK_MOVEMENT_TYPES:
        raise HTTPException(status_code=422, detail="Invalid movement type")
    if from_date is not None and to_date is not None and from_date > to_date:
        raise HTTPException(status_code=422, detail="Invalid date range")
    statement = select(StockMovement)
    if product_id is not None:
        statement = statement.where(StockMovement.product_id == product_id)
    if from_date is not None:
        statement = statement.where(StockMovement.occurred_at >= _utc_boundary(from_date, end_of_day=False))
    if to_date is not None:
        statement = statement.where(StockMovement.occurred_at <= _utc_boundary(to_date, end_of_day=True))
    if movement_type is not None:
        statement = statement.where(StockMovement.movement_type == movement_type)
    if source_type is not None:
        statement = statement.where(StockMovement.source_type == source_type)
    if source_id is not None:
        statement = statement.where(StockMovement.source_id == source_id)
    if not include_void:
        statement = statement.where(StockMovement.voided_at.is_(None))
    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    rows = db.scalars(statement.order_by(StockMovement.occurred_at.desc(), StockMovement.id.desc()).offset(offset).limit(limit)).all()
    return StockMovementListResponse(items=[_present_movement(row, user) for row in rows], total=total)
