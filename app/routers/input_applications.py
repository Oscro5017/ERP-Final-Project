from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
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
from ..services.input_catalog import suggest_input_catalog, upsert_input_catalog
from ..services.secure_fields import encrypt_number, encrypt_text, present_number, present_text

router = APIRouter(tags=["input applications"])


def present_input_application(application: InputApplication, role: Role) -> InputApplicationResponse:
    is_masked = role != Role.owner
    return InputApplicationResponse(
        id=application.id,
        cycle_id=application.cycle_id,
        applied_date=application.applied_date,
        category=application.category,
        note=present_text(application.note_encrypted, role) if application.note_encrypted else None,
        is_masked=is_masked,
        items=[
            {
                "id": item.id,
                "item_name": present_text(item.item_name_encrypted, role),
                "quantity": present_number(item.quantity_encrypted, role),
                "unit": item.unit,
                "is_masked": is_masked,
            }
            for item in application.items
        ],
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

    for item_payload in payload.items:
        item_name = (item_payload.item_name or "").strip()
        if not item_name:
            continue

        catalog = upsert_input_catalog(db, item_name, item_payload.unit, payload.category)
        application.items.append(
            InputItem(
                item_name_encrypted=encrypt_text(item_name).encode("ascii"),
                quantity_encrypted=encrypt_number(item_payload.quantity).encode("ascii"),
                unit=item_payload.unit.strip() if item_payload.unit and item_payload.unit.strip() else (catalog.last_unit or ""),
            )
        )

    db.commit()
    db.refresh(application)
    query = active_rows(select(InputApplication).where(InputApplication.id == application.id), InputApplication)
    created = db.scalar(query.options(selectinload(InputApplication.items)))
    return present_input_application(created, user.role)


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
        for item_payload in payload.items:
            item_name = (item_payload.item_name or "").strip()
            if not item_name:
                continue
            catalog = upsert_input_catalog(db, item_name, item_payload.unit, application.category)
            application.items.append(
                InputItem(
                    item_name_encrypted=encrypt_text(item_name).encode("ascii"),
                    quantity_encrypted=encrypt_number(item_payload.quantity).encode("ascii"),
                    unit=item_payload.unit.strip() if item_payload.unit and item_payload.unit.strip() else (catalog.last_unit or ""),
                )
            )

    db.commit()
    query = active_rows(select(InputApplication).where(InputApplication.id == application.id), InputApplication)
    updated = db.scalar(query.options(selectinload(InputApplication.items)))
    return present_input_application(updated, user.role)


@router.delete("/input-applications/{application_id}", status_code=204)
def delete_input_application(application_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    application = get_active(db, InputApplication, application_id)
    if not application:
        raise HTTPException(status_code=404, detail="Input application not found")
    application.deleted_at = utc_now()
    db.commit()


@router.get("/input-catalog/suggestions", response_model=InputCatalogSuggestionsResponse)
def get_input_catalog_suggestions(q: str = Query(default=""), limit: int = Query(default=10, ge=1, le=20), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if user.role != Role.owner:
        return InputCatalogSuggestionsResponse(items=[], is_masked=True)

    items = suggest_input_catalog(db, q, limit=limit)
    return InputCatalogSuggestionsResponse(
        items=[
            InputCatalogSuggestionResponse(
                id=item.id,
                item_name=present_text(item.name_encrypted, user.role),
                last_unit=item.last_unit,
                last_category=item.last_category,
                last_used_at=item.last_used_at,
                use_count=item.use_count,
            )
            for item in items
        ],
        is_masked=False,
    )
