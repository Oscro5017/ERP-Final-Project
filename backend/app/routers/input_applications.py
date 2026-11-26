from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from ..models import CropCycle, InputApplication, InputItem, Role, User, utc_now
from ..query_helpers import active_rows, get_active
from ..schemas import (
    InputApplicationCreate,
    InputApplicationResponse,
    InputApplicationUpdate,
    InputCatalogSuggestionsResponse,
    InputCatalogSuggestionResponse,
)
from ..security import get_current_user
from ..services.input_catalog import suggest_input_catalog_with_status, upsert_input_catalog
from ..services.input_stock import sync_input_application_stock, validate_input_product
from ..services.products_stock import void_source_movements
from ..services.source_types import INPUT_APPLICATION
from ..services.secure_fields import encrypt_number, encrypt_text, present_number_safe, present_text_safe

router = APIRouter(tags=["input applications"])


def present_input_application(application: InputApplication, role: Role, warnings: list[str] | None = None) -> InputApplicationResponse:
    is_masked = role != Role.owner
    note_result = present_text_safe(
        application.note_encrypted,
        role,
        table="input_applications",
        row_id=application.id,
        field="note",
    )
    presented_items = []
    decrypt_failed = note_result.decrypt_failed
    for item in application.items:
        name_result = present_text_safe(
            item.item_name_encrypted, role, table="input_items", row_id=item.id, field="item_name"
        )
        quantity_result = present_number_safe(
            item.quantity_encrypted, role, table="input_items", row_id=item.id, field="quantity"
        )
        decrypt_failed = decrypt_failed or name_result.decrypt_failed or quantity_result.decrypt_failed
        presented_items.append({
            "id": item.id,
            "item_name": name_result.value,
            "quantity": quantity_result.value,
            "unit": item.unit,
            "product_id": item.product_id,
            "is_masked": is_masked,
            "decrypt_failed": name_result.decrypt_failed or quantity_result.decrypt_failed,
        })

    return InputApplicationResponse(
        id=application.id,
        cycle_id=application.cycle_id,
        applied_date=application.applied_date,
        category=application.category,
        note=note_result.value if application.note_encrypted else None,
        is_masked=is_masked,
        items=presented_items,
        warnings=warnings or [],
        decrypt_failed=decrypt_failed,
    )


@router.get("/crop-cycles/{cycle_id}/input-applications", response_model=list[InputApplicationResponse])
def list_input_applications(cycle_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    cycle = get_active(db, CropCycle, cycle_id)
    if not cycle:
        raise HTTPException(status_code=404, detail="Crop cycle not found")

    rows = (
        db.scalars(
            active_rows(select(InputApplication).where(InputApplication.cycle_id == cycle_id), InputApplication)
            .options(selectinload(InputApplication.items))
            .order_by(InputApplication.applied_date.desc(), InputApplication.id.desc())
        )
        .unique()
        .all()
    )
    return [present_input_application(row, user.role) for row in rows]


@router.post("/crop-cycles/{cycle_id}/input-applications", response_model=InputApplicationResponse, status_code=201)
def create_input_application(cycle_id: int, payload: InputApplicationCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    cycle = get_active(db, CropCycle, cycle_id)
    if not cycle:
        raise HTTPException(status_code=404, detail="Crop cycle not found")
    if not payload.items:
        raise HTTPException(status_code=400, detail="At least one input item is required")

    application = InputApplication(
        cycle_id=cycle_id,
        applied_date=payload.applied_date or date.today(),
        category=payload.category.strip(),
        note_encrypted=encrypt_text(payload.note.strip()).encode("ascii") if payload.note and payload.note.strip() else None,
    )
    db.add(application)
    db.flush()

    movement_items = []
    for item_payload in payload.items:
        item_name = (item_payload.item_name or "").strip()
        if not item_name:
            continue

        catalog = upsert_input_catalog(db, item_name, item_payload.unit, payload.category)
        explicitly_mapped = "product_id" in item_payload.model_fields_set
        if explicitly_mapped:
            try:
                validate_input_product(db, item_payload.product_id)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            catalog.product_id = item_payload.product_id
        product_id = item_payload.product_id if explicitly_mapped else catalog.product_id
        try:
            validate_input_product(db, product_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        application.items.append(
            InputItem(
                item_name_encrypted=encrypt_text(item_name).encode("ascii"),
                quantity_encrypted=encrypt_number(item_payload.quantity).encode("ascii"),
                unit=item_payload.unit.strip() if item_payload.unit and item_payload.unit.strip() else (catalog.last_unit or ""),
                product_id=product_id,
            )
        )
        movement_items.append((application.items[-1], item_payload.quantity))

    warnings = sync_input_application_stock(db, application, movement_items)
    db.commit()
    db.refresh(application)
    query = active_rows(select(InputApplication).where(InputApplication.id == application.id), InputApplication)
    created = db.scalar(query.options(selectinload(InputApplication.items)))
    return present_input_application(created, user.role, warnings)


@router.patch("/input-applications/{application_id}", response_model=InputApplicationResponse)
def update_input_application(application_id: int, payload: InputApplicationUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    query = active_rows(select(InputApplication).where(InputApplication.id == application_id), InputApplication)
    application = db.scalar(query.options(selectinload(InputApplication.items)))
    if not application:
        raise HTTPException(status_code=404, detail="Input application not found")

    if payload.applied_date is not None:
        application.applied_date = payload.applied_date
    if payload.category is not None:
        application.category = payload.category.strip()
    if payload.note is not None:
        application.note_encrypted = encrypt_text(payload.note.strip()).encode("ascii") if payload.note.strip() else None

    if payload.items is not None:
        application.items.clear()
        movement_items = []
        for item_payload in payload.items:
            item_name = (item_payload.item_name or "").strip()
            if not item_name:
                continue
            catalog = upsert_input_catalog(db, item_name, item_payload.unit, application.category)
            explicitly_mapped = "product_id" in item_payload.model_fields_set
            if explicitly_mapped:
                try:
                    validate_input_product(db, item_payload.product_id)
                except ValueError as exc:
                    raise HTTPException(status_code=422, detail=str(exc)) from exc
                catalog.product_id = item_payload.product_id
            product_id = item_payload.product_id if explicitly_mapped else catalog.product_id
            try:
                validate_input_product(db, product_id)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            application.items.append(
                InputItem(
                    item_name_encrypted=encrypt_text(item_name).encode("ascii"),
                    quantity_encrypted=encrypt_number(item_payload.quantity).encode("ascii"),
                    unit=item_payload.unit.strip() if item_payload.unit and item_payload.unit.strip() else (catalog.last_unit or ""),
                    product_id=product_id,
                )
            )
            movement_items.append((application.items[-1], item_payload.quantity))
        warnings = sync_input_application_stock(db, application, movement_items)
    else:
        warnings = []

    db.commit()
    query = active_rows(select(InputApplication).where(InputApplication.id == application.id), InputApplication)
    updated = db.scalar(query.options(selectinload(InputApplication.items)))
    return present_input_application(updated, user.role, warnings)


@router.delete("/input-applications/{application_id}", status_code=204)
def delete_input_application(application_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    application = get_active(db, InputApplication, application_id)
    if not application:
        raise HTTPException(status_code=404, detail="Input application not found")
    void_source_movements(db, INPUT_APPLICATION, application.id)
    application.deleted_at = utc_now()
    db.commit()


@router.get(
    "/input-catalog/suggestions",
    response_model=InputCatalogSuggestionsResponse,
)
def get_input_catalog_suggestions(q: str = Query(default=""), limit: int = Query(default=10, ge=1, le=20), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if user.role != Role.owner:
        return JSONResponse(content={"items": [], "is_masked": True})

    items, decrypt_failed = suggest_input_catalog_with_status(db, q, limit=limit)
    response = InputCatalogSuggestionsResponse(
        items=[
            InputCatalogSuggestionResponse(
                id=item.id,
                item_name=item.name,
                last_unit=item.last_unit,
                last_category=item.last_category,
                last_used_at=item.last_used_at,
                use_count=item.use_count,
                product_id=item.product_id,
                decrypt_failed=False,
            )
            for item in items
        ],
        is_masked=False,
        decrypt_failed=decrypt_failed,
    )
    payload = response.model_dump(mode="json")
    if not decrypt_failed:
        payload.pop("decrypt_failed", None)
    return JSONResponse(content=payload)
