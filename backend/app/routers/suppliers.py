from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Role, Supplier, User, utc_now
from ..query_helpers import active_rows, get_active
from ..schemas import SupplierCreate, SupplierListResponse, SupplierResponse, SupplierUpdate
from ..security import get_current_user
from ..services.secure_fields import encrypt_text, normalize_catalog_name, present_text_safe, safe_decrypt_text, hash_catalog_name

router = APIRouter(prefix="/suppliers", tags=["suppliers"])


def _present(supplier: Supplier, db: Session, role: Role) -> SupplierResponse:
    results = {
        "name": present_text_safe(supplier.name_encrypted, role, table="suppliers", row_id=supplier.id, field="name"),
        "contact": present_text_safe(supplier.contact_encrypted, role, table="suppliers", row_id=supplier.id, field="contact"),
        "area": present_text_safe(supplier.area_encrypted, role, table="suppliers", row_id=supplier.id, field="area"),
        "note": present_text_safe(supplier.note_encrypted, role, table="suppliers", row_id=supplier.id, field="note"),
    }
    duplicates = db.scalar(select(func.count()).select_from(Supplier).where(
        Supplier.name_hash == supplier.name_hash,
        Supplier.deleted_at.is_(None),
        Supplier.id != supplier.id,
    )) or 0
    return SupplierResponse(
        id=supplier.id,
        name=results["name"].value,
        contact=results["contact"].value,
        area=results["area"].value,
        note=results["note"].value,
        is_active=supplier.is_active,
        is_masked=role != Role.owner,
        warnings=["duplicate_name"] if duplicates else [],
        decrypt_failed=any(result.decrypt_failed for result in results.values()),
        created_at=supplier.created_at,
        updated_at=supplier.updated_at,
    )


@router.get("", response_model=SupplierListResponse)
def list_suppliers(
    q: str | None = Query(default=None, max_length=160),
    include_inactive: bool = False,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    statement = active_rows(select(Supplier), Supplier)
    if not include_inactive:
        statement = statement.where(Supplier.is_active.is_(True))
    suppliers = db.scalars(statement.order_by(Supplier.id)).all()
    query = normalize_catalog_name(q) if q else None
    selected = []
    for supplier in suppliers:
        if query:
            value = safe_decrypt_text(supplier.name_encrypted, table="suppliers", row_id=supplier.id, field="name")
            if value.decrypt_failed or query not in normalize_catalog_name(value.value):
                continue
        selected.append(supplier)
    return SupplierListResponse(
        items=[_present(supplier, db, user.role) for supplier in selected[offset:offset + limit]],
        total=len(selected),
    )


@router.post("", response_model=SupplierResponse, status_code=201)
def create_supplier(payload: SupplierCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    name = payload.name.strip()
    if not normalize_catalog_name(name):
        raise HTTPException(status_code=422, detail="Invalid supplier data")
    name_hash = hash_catalog_name(name)
    supplier = Supplier(
        name_encrypted=encrypt_text(name).encode("ascii"),
        name_hash=name_hash,
        contact_encrypted=encrypt_text(payload.contact).encode("ascii") if payload.contact else None,
        area_encrypted=encrypt_text(payload.area).encode("ascii") if payload.area else None,
        note_encrypted=encrypt_text(payload.note).encode("ascii") if payload.note else None,
        is_active=payload.is_active,
    )
    db.add(supplier)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Unable to save supplier")
    db.refresh(supplier)
    return _present(supplier, db, user.role)


@router.get("/{supplier_id}", response_model=SupplierResponse)
def get_supplier(supplier_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    supplier = get_active(db, Supplier, supplier_id)
    if supplier is None:
        raise HTTPException(status_code=404, detail="Supplier not found")
    return _present(supplier, db, user.role)


@router.patch("/{supplier_id}", response_model=SupplierResponse)
def update_supplier(
    supplier_id: int,
    payload: SupplierUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    supplier = get_active(db, Supplier, supplier_id)
    if supplier is None:
        raise HTTPException(status_code=404, detail="Supplier not found")
    changes = payload.model_dump(exclude_unset=True)
    if "name" in changes:
        requested_name = changes.pop("name")
        if requested_name is None:
            raise HTTPException(status_code=422, detail="Invalid supplier data")
        name = requested_name.strip()
        if not normalize_catalog_name(name):
            raise HTTPException(status_code=422, detail="Invalid supplier data")
        name_hash = hash_catalog_name(name)
        supplier.name_encrypted = encrypt_text(name).encode("ascii")
        supplier.name_hash = name_hash
    for field in ("contact", "area", "note"):
        if field in changes:
            value = changes.pop(field)
            setattr(supplier, f"{field}_encrypted", encrypt_text(value).encode("ascii") if value else None)
    for field, value in changes.items():
        setattr(supplier, field, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Unable to update supplier")
    db.refresh(supplier)
    return _present(supplier, db, user.role)


@router.delete("/{supplier_id}", status_code=204)
def delete_supplier(supplier_id: int, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    supplier = get_active(db, Supplier, supplier_id)
    if supplier is None:
        raise HTTPException(status_code=404, detail="Supplier not found")
    supplier.deleted_at = utc_now()
    supplier.is_active = False
    db.commit()
    return Response(status_code=204)
