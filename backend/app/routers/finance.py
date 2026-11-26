from collections import defaultdict
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (
    FINANCE_CATEGORIES,
    FINANCE_DIRECTIONS,
    CropCycle,
    Customer,
    FinanceEntry,
    Role,
    Supplier,
    StockDocument,
    StockDocumentLine,
    User,
    utc_now,
)
from ..schemas import (
    FinanceEntryCreate,
    FinanceEntryListResponse,
    FinanceEntryResponse,
    FinanceEntryUpdate,
    FinanceEntryVoidRequest,
)
from ..security import get_current_user
from ..services.finance_entries import finance_today, validate_manual_amount
from ..services.secure_fields import (
    encrypt_number,
    encrypt_text,
    present_aggregate,
    present_number_safe,
    present_text_safe,
    safe_decrypt_number,
    safe_decrypt_text,
)

router = APIRouter(prefix="/finance", tags=["finance"])
_MAX_AGGREGATE_ROWS = 10_000
_CENT = Decimal("0.01")


def _present_entry(entry: FinanceEntry, role: Role) -> FinanceEntryResponse:
    amount = present_number_safe(entry.amount_encrypted, role, table="finance_entries", row_id=entry.id, field="amount")
    description = present_text_safe(entry.description_encrypted, role, table="finance_entries", row_id=entry.id, field="description")
    reason = present_text_safe(entry.void_reason_encrypted, role, table="finance_entries", row_id=entry.id, field="void_reason")
    return FinanceEntryResponse(
        id=entry.id,
        entry_date=entry.entry_date,
        direction=entry.direction,
        category=entry.category,
        amount=amount.value,
        description=description.value if entry.description_encrypted else None,
        source_type=entry.source_type,
        source_id=entry.source_id,
        crop_cycle_id=entry.crop_cycle_id,
        customer_id=entry.customer_id,
        supplier_id=entry.supplier_id,
        is_auto=entry.is_auto,
        status=entry.status,
        void_reason=reason.value if entry.void_reason_encrypted else None,
        voided_at=entry.voided_at,
        is_masked=role != Role.owner,
        decrypt_failed=amount.decrypt_failed or description.decrypt_failed or reason.decrypt_failed,
        created_at=entry.created_at,
        updated_at=entry.updated_at,
    )


def _check_links(db: Session, payload: FinanceEntryCreate) -> None:
    if payload.crop_cycle_id is not None:
        cycle = db.get(CropCycle, payload.crop_cycle_id)
        if cycle is None or cycle.deleted_at is not None:
            raise HTTPException(status_code=422, detail="Crop cycle is not available")
    if payload.customer_id is not None:
        customer = db.get(Customer, payload.customer_id)
        if customer is None or customer.deleted_at is not None:
            raise HTTPException(status_code=422, detail="Customer is not available")
    if payload.supplier_id is not None:
        supplier = db.get(Supplier, payload.supplier_id)
        if supplier is None or supplier.deleted_at is not None or not supplier.is_active:
            raise HTTPException(status_code=422, detail="Supplier is not available")


@router.post("/entries", response_model=FinanceEntryResponse, status_code=201)
def create_manual_entry(payload: FinanceEntryCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _check_links(db, payload)
    try:
        amount = validate_manual_amount(payload.amount)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    entry = FinanceEntry(
        entry_date=payload.entry_date or finance_today(),
        direction=payload.direction,
        category=payload.category,
        amount_encrypted=encrypt_number(amount).encode("ascii"),
        description_encrypted=encrypt_text(payload.description).encode("ascii") if payload.description else None,
        crop_cycle_id=payload.crop_cycle_id,
        customer_id=payload.customer_id,
        supplier_id=payload.supplier_id,
        is_auto=False,
        status="posted",
        created_by=user.id,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return _present_entry(entry, user.role)


@router.get("/entries", response_model=FinanceEntryListResponse)
def list_entries(
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    direction: str | None = None,
    category: str | None = None,
    crop_cycle_id: int | None = Query(default=None, gt=0),
    customer_id: int | None = Query(default=None, gt=0),
    supplier_id: int | None = Query(default=None, gt=0),
    status: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if direction is not None and direction not in FINANCE_DIRECTIONS:
        raise HTTPException(status_code=422, detail="Invalid direction")
    if category is not None and category not in FINANCE_CATEGORIES:
        raise HTTPException(status_code=422, detail="Invalid category")
    if status is not None and status not in {"posted", "void"}:
        raise HTTPException(status_code=422, detail="Invalid status")
    if from_date is not None and to_date is not None and from_date > to_date:
        raise HTTPException(status_code=422, detail="Invalid date range")
    statement = select(FinanceEntry)
    if from_date is not None:
        statement = statement.where(FinanceEntry.entry_date >= from_date)
    if to_date is not None:
        statement = statement.where(FinanceEntry.entry_date <= to_date)
    for column, value in (
        (FinanceEntry.direction, direction),
        (FinanceEntry.category, category),
        (FinanceEntry.crop_cycle_id, crop_cycle_id),
        (FinanceEntry.customer_id, customer_id),
        (FinanceEntry.supplier_id, supplier_id),
        (FinanceEntry.status, status),
    ):
        if value is not None:
            statement = statement.where(column == value)
    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    rows = db.scalars(statement.order_by(FinanceEntry.entry_date.desc(), FinanceEntry.id.desc()).offset(offset).limit(limit)).all()
    return FinanceEntryListResponse(items=[_present_entry(row, user.role) for row in rows], total=total)


@router.patch("/entries/{entry_id}", response_model=FinanceEntryResponse)
def update_manual_entry(
    entry_id: int,
    payload: FinanceEntryUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    entry = db.get(FinanceEntry, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Finance entry not found")
    if entry.is_auto:
        raise HTTPException(status_code=409, detail="Automatic finance entries cannot be edited directly")
    if entry.status != "posted":
        raise HTTPException(status_code=409, detail="Voided finance entry cannot be edited")
    changes = payload.model_dump(exclude_unset=True)
    if "amount" in changes:
        try:
            amount = validate_manual_amount(changes.pop("amount"))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        entry.amount_encrypted = encrypt_number(amount).encode("ascii")
    if "description" in changes:
        value = changes.pop("description")
        entry.description_encrypted = encrypt_text(value).encode("ascii") if value else None
    for key, value in changes.items():
        setattr(entry, key, value)
    db.commit()
    db.refresh(entry)
    return _present_entry(entry, user.role)


@router.post("/entries/{entry_id}/void", response_model=FinanceEntryResponse)
def void_entry(
    entry_id: int,
    payload: FinanceEntryVoidRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    entry = db.get(FinanceEntry, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Finance entry not found")
    if entry.is_auto:
        raise HTTPException(status_code=409, detail="Void the source document instead")
    if entry.status != "posted":
        raise HTTPException(status_code=409, detail="Finance entry is already void")
    entry.status = "void"
    entry.voided_at = utc_now()
    entry.void_reason_encrypted = encrypt_text(payload.reason).encode("ascii") if payload.reason else None
    db.commit()
    db.refresh(entry)
    return _present_entry(entry, user.role)


def _season_key(value: date) -> str:
    if value.month in {3, 4, 5}:
        return f"summer_{value.year}"
    if value.month in {6, 7, 8, 9, 10}:
        return f"rainy_{value.year}"
    start_year = value.year if value.month >= 11 else value.year - 1
    return f"winter_{start_year}_{start_year + 1}"


def _date_group_key(value: date, group_by: str) -> str:
    if group_by == "month":
        return value.strftime("%Y-%m")
    if group_by == "quarter":
        return f"{value.year}-Q{(value.month - 1) // 3 + 1}"
    if group_by == "season":
        return _season_key(value)
    return "all"


def _group_key(entry: FinanceEntry, group_by: str) -> str:
    if group_by in {"month", "quarter", "season"}:
        return _date_group_key(entry.entry_date, group_by)
    if group_by == "category":
        return entry.category
    if group_by == "cycle":
        return str(entry.crop_cycle_id) if entry.crop_cycle_id is not None else "unallocated"
    if group_by == "customer":
        return str(entry.customer_id) if entry.customer_id is not None else "unallocated"
    return "all"


def _load_customer_areas(db: Session, customer_ids: set[int]) -> tuple[dict[int, str | None], set[int]]:
    if not customer_ids:
        return {}, set()
    rows = db.execute(select(Customer.id, Customer.area_encrypted).where(Customer.id.in_(customer_ids))).all()
    areas: dict[int, str | None] = {}
    failed: set[int] = set()
    for customer_id, token in rows:
        if token is None:
            areas[customer_id] = None
            continue
        result = safe_decrypt_text(token, table="customers", row_id=customer_id, field="area")
        if result.decrypt_failed:
            failed.add(customer_id)
        else:
            areas[customer_id] = result.value or None
    return areas, failed


def _aggregate_rows(db: Session, entries: list[FinanceEntry], group_by: str, role: Role):
    grouped = defaultdict(lambda: {"income": Decimal("0"), "expense": Decimal("0"), "entry_count": 0})
    unallocated_expense = Decimal("0")
    skipped = 0
    customer_areas: dict[int, str | None] = {}
    failed_area_ids: set[int] = set()
    if group_by == "area":
        customer_ids = {entry.customer_id for entry in entries if entry.customer_id is not None}
        customer_areas, failed_area_ids = _load_customer_areas(db, customer_ids)
    for entry in entries:
        result = safe_decrypt_number(entry.amount_encrypted, table="finance_entries", row_id=entry.id, field="amount")
        if result.decrypt_failed or result.value is None:
            skipped += 1
            continue
        amount = result.value
        if group_by == "area":
            if entry.customer_id in failed_area_ids:
                skipped += 1
                continue
            key = customer_areas.get(entry.customer_id) if entry.customer_id is not None else None
            key = key or "unspecified"
        else:
            key = _group_key(entry, group_by)
        grouped[key][entry.direction] += amount
        grouped[key]["entry_count"] += 1
        if entry.direction == "expense" and entry.crop_cycle_id is None:
            unallocated_expense += amount
    rows = []
    for key in sorted(grouped):
        values = grouped[key]
        profit = values["income"] - values["expense"]
        masked_key = encrypt_text(key) if group_by == "area" and key != "unspecified" and role != Role.owner else key
        row = {
            "key": masked_key,
            "income": present_aggregate(values["income"], role),
            "expense": present_aggregate(values["expense"], role),
            "profit": present_aggregate(profit, role),
            "entry_count": values["entry_count"],
        }
        if group_by == "area":
            row["is_masked"] = role != Role.owner
        rows.append(row)
    return rows, skipped, unallocated_expense


def _load_bounded_entries(db: Session, statement):
    rows = db.scalars(statement.order_by(FinanceEntry.entry_date, FinanceEntry.id).limit(_MAX_AGGREGATE_ROWS + 1)).all()
    return rows[:_MAX_AGGREGATE_ROWS], len(rows) > _MAX_AGGREGATE_ROWS


def _validate_report_range(from_date: date, to_date: date) -> None:
    if from_date > to_date or (to_date - from_date).days + 1 > 366:
        raise HTTPException(status_code=422, detail="Date range must be between 1 and 366 days")


@router.get("/summary")
def finance_summary(
    from_date: date = Query(alias="from"),
    to_date: date = Query(alias="to"),
    group_by: str = "none",
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _validate_report_range(from_date, to_date)
    if group_by not in {"none", "month", "quarter", "season", "category", "cycle", "customer", "area"}:
        raise HTTPException(status_code=422, detail="Invalid group_by")
    statement = select(FinanceEntry).where(
        FinanceEntry.status == "posted",
        FinanceEntry.entry_date >= from_date,
        FinanceEntry.entry_date <= to_date,
    )
    entries, truncated = _load_bounded_entries(db, statement)
    items, skipped, unallocated = _aggregate_rows(db, entries, group_by, user.role)
    return {
        "items": items,
        "unallocated_expense": present_aggregate(unallocated, user.role),
        "skipped_decrypt_failed": skipped,
        "truncated": truncated,
    }


@router.get("/cycles/{cycle_id}/pnl")
def cycle_profit_and_loss(cycle_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    cycle = db.get(CropCycle, cycle_id)
    if cycle is None or cycle.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Crop cycle not found")
    statement = select(FinanceEntry).where(FinanceEntry.status == "posted", FinanceEntry.crop_cycle_id == cycle_id)
    entries, truncated = _load_bounded_entries(db, statement)
    revenue = Decimal("0")
    cost = Decimal("0")
    skipped = 0
    categories = defaultdict(lambda: {"income": Decimal("0"), "expense": Decimal("0"), "entry_count": 0})
    for entry in entries:
        result = safe_decrypt_number(entry.amount_encrypted, table="finance_entries", row_id=entry.id, field="amount")
        if result.decrypt_failed or result.value is None:
            skipped += 1
            continue
        categories[entry.category][entry.direction] += result.value
        categories[entry.category]["entry_count"] += 1
        if entry.direction == "income":
            revenue += result.value
        else:
            cost += result.value
    profit = revenue - cost
    margin = (profit / revenue * Decimal("100")).quantize(_CENT, rounding=ROUND_HALF_UP) if revenue > 0 else None
    quantity = Decimal(str(cycle.harvest_quantity_kg)) if cycle.harvest_quantity_kg is not None else None
    cost_per_kg = (cost / quantity).quantize(_CENT, rounding=ROUND_HALF_UP) if quantity and quantity > 0 else None
    category_rows = [{
        "category": key,
        "income": present_aggregate(value["income"], user.role),
        "expense": present_aggregate(value["expense"], user.role),
        "entry_count": value["entry_count"],
    } for key, value in sorted(categories.items())]
    return {
        "cycle_id": cycle_id,
        "revenue": present_aggregate(revenue, user.role),
        "cost": present_aggregate(cost, user.role),
        "profit": present_aggregate(profit, user.role),
        "margin_pct": present_aggregate(margin, user.role) if margin is not None else None,
        "harvest_quantity_kg": cycle.harvest_quantity_kg,
        "cost_per_kg": present_aggregate(cost_per_kg, user.role) if cost_per_kg is not None else None,
        "categories": category_rows,
        "skipped_decrypt_failed": skipped,
        "truncated": truncated,
    }


@router.get("/prices")
def price_trends(
    from_date: date = Query(alias="from"),
    to_date: date = Query(alias="to"),
    product_id: int | None = Query(default=None, gt=0),
    group_by: str = "month",
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _validate_report_range(from_date, to_date)
    if group_by not in {"month", "quarter", "season", "customer", "area"}:
        raise HTTPException(status_code=422, detail="Invalid group_by")
    statement = select(StockDocumentLine, StockDocument).join(
        StockDocument, StockDocument.id == StockDocumentLine.document_id
    ).where(
        StockDocument.doc_type == "outbound",
        StockDocument.status == "posted",
        StockDocument.doc_date >= from_date,
        StockDocument.doc_date <= to_date,
        StockDocumentLine.unit_price_encrypted.is_not(None),
    )
    if product_id is not None:
        statement = statement.where(StockDocumentLine.product_id == product_id)
    rows = db.execute(statement.order_by(StockDocument.doc_date, StockDocument.id, StockDocumentLine.id).limit(_MAX_AGGREGATE_ROWS + 1)).all()
    truncated = len(rows) > _MAX_AGGREGATE_ROWS
    customer_ids = {document.customer_id for _line, document in rows[:_MAX_AGGREGATE_ROWS] if document.customer_id is not None} if group_by == "area" else set()
    customer_areas, failed_area_ids = _load_customer_areas(db, customer_ids)
    groups = defaultdict(lambda: {"weighted_total": Decimal("0"), "total_quantity": Decimal("0"), "min": None, "max": None, "line_count": 0})
    skipped = 0
    for line, document in rows[:_MAX_AGGREGATE_ROWS]:
        price = safe_decrypt_number(line.unit_price_encrypted, table="stock_document_lines", row_id=line.id, field="unit_price")
        if price.decrypt_failed or price.value is None:
            skipped += 1
            continue
        if group_by == "area":
            if document.customer_id in failed_area_ids:
                skipped += 1
                continue
            area = customer_areas.get(document.customer_id) if document.customer_id is not None else None
            key = area or "unspecified"
        else:
            key = str(document.customer_id) if group_by == "customer" and document.customer_id is not None else (
                "unallocated" if group_by == "customer" else _date_group_key(document.doc_date, group_by)
            )
        value = groups[key]
        quantity = Decimal(str(line.quantity))
        value["weighted_total"] += price.value * quantity
        value["total_quantity"] += quantity
        value["min"] = price.value if value["min"] is None else min(value["min"], price.value)
        value["max"] = price.value if value["max"] is None else max(value["max"], price.value)
        value["line_count"] += 1
    items = []
    for key in sorted(groups):
        value = groups[key]
        average = (value["weighted_total"] / value["total_quantity"]).quantize(_CENT, rounding=ROUND_HALF_UP) if value["total_quantity"] else Decimal("0")
        masked_key = encrypt_text(key) if group_by == "area" and key != "unspecified" and user.role != Role.owner else key
        item = {
            "key": masked_key,
            "weighted_avg_price": present_aggregate(average, user.role),
            "min": present_aggregate(value["min"], user.role),
            "max": present_aggregate(value["max"], user.role),
            "line_count": value["line_count"],
            "total_quantity": float(value["total_quantity"].quantize(Decimal("0.001"))),
        }
        if group_by == "area":
            item["is_masked"] = user.role != Role.owner
        items.append(item)
    return {"items": items, "skipped_decrypt_failed": skipped, "truncated": truncated}


@router.get("/customers/revenue")
def customer_revenue(
    from_date: date = Query(alias="from"),
    to_date: date = Query(alias="to"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _validate_report_range(from_date, to_date)
    statement = select(FinanceEntry).where(
        FinanceEntry.status == "posted",
        FinanceEntry.direction == "income",
        FinanceEntry.entry_date >= from_date,
        FinanceEntry.entry_date <= to_date,
    )
    entries, truncated = _load_bounded_entries(db, statement)
    totals: dict[int | None, Decimal] = defaultdict(lambda: Decimal("0"))
    skipped = 0
    for entry in entries:
        result = safe_decrypt_number(entry.amount_encrypted, table="finance_entries", row_id=entry.id, field="amount")
        if result.decrypt_failed or result.value is None:
            skipped += 1
            continue
        totals[entry.customer_id] += result.value
    total_income = sum(totals.values(), Decimal("0"))
    ranked = sorted(totals.items(), key=lambda item: (-item[1], item[0] if item[0] is not None else 0))
    items = []
    for rank, (customer_id, income) in enumerate(ranked, start=1):
        customer = db.get(Customer, customer_id) if customer_id is not None else None
        name = present_text_safe(
            customer.name_encrypted if customer else None,
            user.role,
            table="customers",
            row_id=customer.id if customer else (customer_id or 0),
            field="name",
        ) if customer else None
        share = (income / total_income * Decimal("100")).quantize(_CENT, rounding=ROUND_HALF_UP) if total_income else Decimal("0")
        items.append({
            "customer_id": customer_id,
            "customer_name": name.value if name else None,
            "income": present_aggregate(income, user.role),
            "share_pct": present_aggregate(share, user.role),
            "rank": rank,
            "is_masked": bool(name and user.role != Role.owner),
        })
    return {"items": items, "skipped_decrypt_failed": skipped, "truncated": truncated}
