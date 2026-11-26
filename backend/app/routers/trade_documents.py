from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (
    STOCK_DOCUMENT_TYPES,
    Role,
    SalesOrderDelivery,
    StockDocument,
    StockDocumentLine,
    StockDocumentPurpose,
    User,
)
from ..schemas import (
    InboundDocumentCreate,
    LastPriceResponse,
    OutboundDocumentCreate,
    StockDocumentListResponse,
    StockDocumentResponse,
    StockDocumentUpdate,
    StockDocumentVoidRequest,
)
from ..security import get_current_user
from ..services.secure_fields import encrypt_text
from ..services.finance_entries import (
    create_auto_finance_for_document,
    document_finance_entry,
    void_auto_finance_for_document,
)
from ..services.sales_orders import reopen_for_voided_document, replan_open_orders
from ..services.stock_documents import (
    create_stock_document,
    last_unit_prices,
    present_stock_document,
    void_stock_document,
)

router = APIRouter(tags=["trade documents"])


def _list_query(
    db: Session,
    doc_type: str | None,
    from_date: date | None,
    to_date: date | None,
    supplier_id: int | None,
    customer_id: int | None,
    product_id: int | None,
    status: str | None,
    sales_only: bool = False,
):
    if doc_type is not None and doc_type not in STOCK_DOCUMENT_TYPES:
        raise HTTPException(status_code=422, detail="Invalid document type")
    if status is not None and status not in {"posted", "void"}:
        raise HTTPException(status_code=422, detail="Invalid document status")
    if from_date is not None and to_date is not None and from_date > to_date:
        raise HTTPException(status_code=422, detail="Invalid date range")
    ids = select(StockDocument.id)
    if product_id is not None:
        ids = ids.join(StockDocumentLine, StockDocumentLine.document_id == StockDocument.id).where(
            StockDocumentLine.product_id == product_id
        ).distinct()
    if doc_type is not None:
        ids = ids.where(StockDocument.doc_type == doc_type)
    if from_date is not None:
        ids = ids.where(StockDocument.doc_date >= from_date)
    if to_date is not None:
        ids = ids.where(StockDocument.doc_date <= to_date)
    if supplier_id is not None:
        ids = ids.where(StockDocument.supplier_id == supplier_id)
    if customer_id is not None:
        ids = ids.where(StockDocument.customer_id == customer_id)
    if sales_only:
        ids = ids.where(
            StockDocument.doc_type == "outbound",
            or_(
                StockDocument.id.in_(select(StockDocumentPurpose.document_id).where(
                    StockDocumentPurpose.purpose.in_(("sale", "order"))
                )),
                StockDocument.id.in_(select(SalesOrderDelivery.document_id)),
                StockDocument.id.not_in(select(StockDocumentPurpose.document_id)),
            ),
        )
    if status is not None:
        ids = ids.where(StockDocument.status == status)
    total = db.scalar(select(func.count()).select_from(ids.subquery())) or 0
    statement = select(StockDocument).where(StockDocument.id.in_(ids)).order_by(
        StockDocument.doc_date.desc(), StockDocument.id.desc()
    )
    return statement, total


@router.post("/trade/inbound", response_model=StockDocumentResponse, status_code=201)
def post_inbound(
    payload: InboundDocumentCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return _create_document(db, "inbound", payload, user)


@router.post("/trade/outbound", response_model=StockDocumentResponse, status_code=201)
def post_outbound(
    payload: OutboundDocumentCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return _create_document(db, "outbound", payload, user)


def _create_document(db: Session, doc_type: str, payload, user: User):
    for attempt in range(3):
        try:
            document, warnings = create_stock_document(db, doc_type, payload, user.id)
            record_finance = payload.record_finance
            if record_finance is None:
                record_finance = getattr(payload, "purpose", None) != "other"
            if record_finance:
                create_auto_finance_for_document(db, document, user.id)
            replan_open_orders(db)
            db.commit()
        except ValueError:
            db.rollback()
            raise HTTPException(status_code=422, detail="Invalid stock document")
        except IntegrityError as exc:
            db.rollback()
            if "doc_no" in str(exc.orig).casefold() and attempt < 2:
                continue
            raise HTTPException(status_code=409, detail="Unable to post stock document")
        db.refresh(document)
        return present_stock_document(db, document, user.role, warnings)
    raise HTTPException(status_code=409, detail="Unable to allocate a document number")


@router.get("/trade/documents", response_model=StockDocumentListResponse)
def list_documents(
    doc_type: str | None = None,
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    supplier_id: int | None = Query(default=None, gt=0),
    customer_id: int | None = Query(default=None, gt=0),
    product_id: int | None = Query(default=None, gt=0),
    status: str | None = None,
    sales_only: bool = False,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    statement, total = _list_query(db, doc_type, from_date, to_date, supplier_id, customer_id, product_id, status, sales_only)
    rows = db.scalars(statement.limit(limit).offset(offset)).all()
    return StockDocumentListResponse(
        items=[present_stock_document(db, row, user.role) for row in rows],
        total=total,
    )


@router.get("/trade/last-prices", response_model=list[LastPriceResponse])
def list_last_prices(
    doc_type: str = Query(default="outbound", pattern="^(inbound|outbound)$"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return last_unit_prices(db, doc_type) if user.role == Role.owner else []


@router.post("/trade/documents/{document_id}/finance", response_model=StockDocumentResponse)
def record_document_finance(document_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    document = db.get(StockDocument, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Stock document not found")
    if document.status != "posted":
        raise HTTPException(status_code=409, detail="Document is voided")
    if document_finance_entry(db, document.id) is not None:
        raise HTTPException(status_code=409, detail="Finance is already recorded for this document")
    try:
        entry = create_auto_finance_for_document(db, document, user.id)
        if entry is None:
            raise HTTPException(status_code=422, detail="Document has no priced lines")
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Finance is already recorded for this document")
    return present_stock_document(db, document, user.role)


@router.get("/trade/documents/{document_id}", response_model=StockDocumentResponse)
def get_document(document_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    document = db.get(StockDocument, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Stock document not found")
    return present_stock_document(db, document, user.role)


@router.patch("/trade/documents/{document_id}", response_model=StockDocumentResponse)
def update_document(
    document_id: int,
    payload: StockDocumentUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    document = db.get(StockDocument, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Stock document not found")
    if document.status != "posted":
        raise HTTPException(status_code=409, detail="Voided document cannot be edited")
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        if field == "note":
            document.note_encrypted = encrypt_text(value).encode("ascii") if value else None
        else:
            document.reference_no = value
    db.commit()
    db.refresh(document)
    return present_stock_document(db, document, user.role)


@router.post("/trade/documents/{document_id}/void", response_model=StockDocumentResponse)
def void_document(
    document_id: int,
    payload: StockDocumentVoidRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    document = db.get(StockDocument, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Stock document not found")
    try:
        void_stock_document(db, document, payload.reason)
        void_auto_finance_for_document(db, document, payload.reason)
        reopen_for_voided_document(db, document.id)
        replan_open_orders(db)
        db.commit()
    except ValueError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Stock document is already voided")
    except RuntimeError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Stock document movement ledger is inconsistent")
    db.refresh(document)
    return present_stock_document(db, document, user.role)
