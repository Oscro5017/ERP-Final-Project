from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import PRODUCT_CATEGORIES, Product, Role, StockMovement, User, utc_now
from ..query_helpers import active_rows, get_active
from ..schemas import (
    ProductAdjustmentCreate, ProductCreate, ProductListResponse, ProductMovementResponse,
    ProductResponse, ProductUpdate,
)
from ..security import get_current_user
from ..services.products_stock import convert_quantity, on_hand, on_hand_grouped, record_movement, sync_product_low_stock_reminder
from ..services.secure_fields import encrypt_text, hash_catalog_name, normalize_catalog_name, present_text_safe, safe_decrypt_text

router = APIRouter(prefix="/products", tags=["products"])


def _present(product: Product, balance: float, role: Role) -> ProductResponse:
    result = present_text_safe(product.name_encrypted, role, table="products", row_id=product.id, field="name")
    return ProductResponse(
        id=product.id, category=product.category, name=result.value, unit=product.unit,
        reorder_point=product.reorder_point, on_hand=balance,
        is_low=balance <= product.reorder_point if product.reorder_point is not None else None,
        is_negative=balance < 0, is_active=product.is_active, is_masked=role != Role.owner,
        decrypt_failed=result.decrypt_failed, created_at=product.created_at, updated_at=product.updated_at,
    )


@router.get("", response_model=ProductListResponse)
def list_products(
    category: str | None = None, q: str | None = Query(default=None, max_length=160),
    include_inactive: bool = False, limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0), db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    statement = active_rows(select(Product), Product)
    if category is not None:
        if category not in PRODUCT_CATEGORIES:
            raise HTTPException(status_code=422, detail="Invalid category")
        statement = statement.where(Product.category == category)
    if not include_inactive:
        statement = statement.where(Product.is_active.is_(True))
    products = db.scalars(statement.order_by(Product.id)).all()
    balances = on_hand_grouped(db, [p.id for p in products])
    query = normalize_catalog_name(q) if q else None
    selected = []
    for product in products:
        if query:
            search_result = safe_decrypt_text(product.name_encrypted, table="products", row_id=product.id, field="name")
            if search_result.decrypt_failed or query not in normalize_catalog_name(search_result.value):
                continue
        selected.append((product, _present(product, balances.get(product.id, 0.0), user.role)))
    total = len(selected)
    return ProductListResponse(items=[resp for _, resp in selected[offset:offset + limit]], total=total)


@router.post("", response_model=ProductResponse, status_code=201)
def create_product(payload: ProductCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if payload.category not in PRODUCT_CATEGORIES:
        raise HTTPException(status_code=422, detail="Invalid category")
    normalized_name = normalize_catalog_name(payload.name)
    if not normalized_name:
        raise HTTPException(status_code=422, detail="Invalid product data")
    name_hash = hash_catalog_name(payload.name)
    if db.scalar(select(Product.id).where(Product.name_hash == name_hash, Product.deleted_at.is_(None))) is not None:
        raise HTTPException(status_code=409, detail="A product with this name already exists")
    product = Product(
        category=payload.category, name_encrypted=encrypt_text(payload.name.strip()).encode("ascii"),
        name_hash=name_hash, unit=payload.unit.strip(),
        reorder_point=payload.reorder_point, is_active=payload.is_active,
    )
    db.add(product)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="A product with this name already exists")
    db.refresh(product)
    return _present(product, 0.0, user.role)


@router.patch("/{product_id}", response_model=ProductResponse)
def update_product(product_id: int, payload: ProductUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    product = get_active(db, Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    changes = payload.model_dump(exclude_unset=True)
    if "category" in changes and changes["category"] not in PRODUCT_CATEGORIES:
        raise HTTPException(status_code=422, detail="Invalid category")
    if "unit" in changes and changes["unit"].strip().casefold() != product.unit.strip().casefold():
        if db.scalar(select(func.count()).select_from(StockMovement).where(StockMovement.product_id == product_id)):
            raise HTTPException(status_code=409, detail="Product unit cannot be changed after stock movements exist")
    if "name" in changes:
        if not normalize_catalog_name(changes["name"]):
            raise HTTPException(status_code=422, detail="Invalid product data")
        new_name = changes.pop("name").strip()
        new_hash = hash_catalog_name(new_name)
        duplicate = db.scalar(select(Product.id).where(
            Product.name_hash == new_hash, Product.deleted_at.is_(None), Product.id != product_id
        ))
        if duplicate is not None:
            raise HTTPException(status_code=409, detail="A product with this name already exists")
        product.name_encrypted = encrypt_text(new_name).encode("ascii")
        product.name_hash = new_hash
    for key, value in changes.items():
        setattr(product, key, value.strip() if key == "unit" else value)
    if "reorder_point" in changes:
        sync_product_low_stock_reminder(db, product)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="A product with this name already exists")
    db.refresh(product)
    return _present(product, on_hand(db, product_id), user.role)


@router.delete("/{product_id}", status_code=204)
def delete_product(product_id: int, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    product = get_active(db, Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    product.deleted_at = utc_now()
    db.commit()
    return Response(status_code=204)


@router.get("/{product_id}/movements", response_model=list[ProductMovementResponse])
def list_product_movements(
    product_id: int, limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    if get_active(db, Product, product_id) is None:
        raise HTTPException(status_code=404, detail="Product not found")
    movements = db.scalars(select(StockMovement).where(StockMovement.product_id == product_id)
                           .order_by(StockMovement.occurred_at.desc(), StockMovement.id.desc())
                           .offset(offset).limit(limit)).all()
    responses = []
    for movement in movements:
        note_result = present_text_safe(movement.note_encrypted, user.role, table="stock_movements", row_id=movement.id, field="note")
        responses.append(ProductMovementResponse(
            id=movement.id, product_id=movement.product_id, quantity_delta=movement.quantity_delta,
            movement_type=movement.movement_type, source_type=movement.source_type, source_id=movement.source_id,
            occurred_at=movement.occurred_at, note=note_result.value if movement.note_encrypted else None,
            voided=movement.voided_at is not None, created_at=movement.created_at, updated_at=movement.updated_at,
            decrypt_failed=note_result.decrypt_failed, is_masked=user.role != Role.owner,
        ))
    return responses


@router.post("/{product_id}/adjustments", response_model=ProductResponse)
def adjust_product(product_id: int, payload: ProductAdjustmentCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    product = get_active(db, Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    try:
        counted = convert_quantity(payload.counted_quantity, payload.unit or product.unit, product.unit)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid quantity or unit")
    balance = on_hand(db, product_id)
    delta = round(counted - balance, 3)
    if delta:
        try:
            record_movement(db, product_id, delta, product.unit, "adjustment", occurred_at=payload.occurred_at, note=payload.note)
            db.commit()
        except ValueError:
            db.rollback()
            raise HTTPException(status_code=422, detail="Invalid quantity or unit")
        db.refresh(product)
        balance = on_hand(db, product_id)
    return _present(product, balance, user.role)
