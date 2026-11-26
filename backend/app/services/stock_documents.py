import logging
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import (
    CropCycle,
    Customer,
    Product,
    SalesOrder,
    SalesOrderDelivery,
    SalesOrderLine,
    StockDocument,
    StockDocumentLine,
    StockDocumentPurpose,
    StockMovement,
    STOCK_DOCUMENT_TYPES,
    Supplier,
    utc_now,
)
from ..schemas import InboundDocumentCreate, OutboundDocumentCreate
from .finance_entries import document_finance_entry
from .freshness import expired_lot_warnings
from .products_stock import convert_quantity, on_hand_grouped, record_movement, start_of_day, void_source_movements
from .secure_fields import (
    encrypt_number,
    encrypt_text,
    present_aggregate,
    present_number_safe,
    present_text_safe,
    safe_decrypt_number,
)
from .source_types import STOCK_DOCUMENT

logger = logging.getLogger(__name__)
_BANGKOK = ZoneInfo("Asia/Bangkok")
_QUANTITY = Decimal("0.001")
_MONEY = Decimal("0.01")


def _today_bangkok() -> date:
    return datetime.now(_BANGKOK).date()


def _document_date(value: date | None) -> date:
    today = _today_bangkok()
    result = value or today
    try:
        upper_bound = today.replace(year=today.year + 1)
    except ValueError:
        upper_bound = today.replace(month=2, day=28, year=today.year + 1)
    if result > upper_bound:
        raise ValueError("Document date is too far in the future")
    return result


def _money(value: Decimal | None) -> Decimal | None:
    if value is None:
        return None
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("Invalid amount") from exc
    if not amount.is_finite() or amount < 0:
        raise ValueError("Invalid amount")
    return amount.quantize(_MONEY, rounding=ROUND_HALF_UP)


def _line_amount(quantity: Decimal, unit_price: Decimal | None, line_amount: Decimal | None):
    price = _money(unit_price)
    supplied_amount = _money(line_amount)
    if price is None:
        if supplied_amount is not None:
            raise ValueError("Line amount requires a unit price")
        return None, None
    calculated = (quantity * price).quantize(_MONEY, rounding=ROUND_HALF_UP)
    if supplied_amount is not None and abs(calculated - supplied_amount) > _MONEY:
        raise ValueError("Unit price and line amount do not match")
    return price, supplied_amount if supplied_amount is not None else calculated


def _next_doc_no(db: Session, doc_type: str, doc_date: date) -> str:
    prefix = ("IN" if doc_type == "inbound" else "OUT") + f"-{doc_date:%y%m%d}-"
    existing = db.scalars(select(StockDocument.doc_no).where(StockDocument.doc_no.like(prefix + "%"))).all()
    sequence = max((int(value.rsplit("-", 1)[1]) for value in existing), default=0) + 1
    return f"{prefix}{sequence:03d}"


def _validate_header_links(db: Session, doc_type: str, payload) -> None:
    if doc_type not in STOCK_DOCUMENT_TYPES:
        raise ValueError("Invalid document type")
    if doc_type == "inbound":
        if getattr(payload, "customer_id", None) is not None:
            raise ValueError("Inbound document cannot reference a customer")
        supplier_id = getattr(payload, "supplier_id", None)
        supplier = db.get(Supplier, supplier_id) if supplier_id is not None else None
        if supplier_id is not None and (supplier is None or supplier.deleted_at is not None or not supplier.is_active):
            raise ValueError("Supplier is not available")
    else:
        if getattr(payload, "supplier_id", None) is not None:
            raise ValueError("Outbound document cannot reference a supplier")
        customer_id = getattr(payload, "customer_id", None)
        customer = db.get(Customer, customer_id) if customer_id is not None else None
        if customer_id is not None and (customer is None or customer.deleted_at is not None):
            raise ValueError("Customer is not available")
    crop_cycle_id = getattr(payload, "crop_cycle_id", None)
    if crop_cycle_id is not None:
        cycle = db.get(CropCycle, crop_cycle_id)
        if cycle is None or cycle.deleted_at is not None:
            raise ValueError("Crop cycle is not available")


def _validate_lines(db: Session, payload_lines):
    validated = []
    warnings: set[str] = set()
    for line_no, line in enumerate(payload_lines, start=1):
        product = db.get(Product, line.product_id)
        if product is None or product.deleted_at is not None:
            raise ValueError("Product is not available")
        if not product.is_active:
            raise ValueError("Product is not active")
        try:
            quantity = Decimal(str(line.quantity))
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise ValueError("Invalid quantity") from exc
        if not quantity.is_finite() or quantity <= 0:
            raise ValueError("Invalid quantity")
        quantity = quantity.quantize(_QUANTITY, rounding=ROUND_HALF_UP)
        if quantity <= 0:
            raise ValueError("Invalid quantity")
        unit = (line.unit or product.unit).strip()
        price, amount = _line_amount(quantity, line.unit_price, line.line_amount)
        base_quantity = None
        try:
            base_quantity = convert_quantity(quantity, unit, product.unit)
            if base_quantity <= 0:
                raise ValueError("Invalid quantity")
        except ValueError:
            warnings.add(f"unit_mismatch:{product.id}")
            logger.warning("Stock document unit mismatch product_id=%s", product.id)
        validated.append({
            "line_no": line_no,
            "product": product,
            "quantity": quantity,
            "unit": unit,
            "base_quantity": base_quantity,
            "unit_price": price,
            "line_amount": amount,
        })
    return validated, sorted(warnings)


def create_stock_document(db: Session, doc_type: str, payload, created_by: int | None = None):
    _validate_header_links(db, doc_type, payload)
    doc_date = _document_date(payload.doc_date)
    lines, warnings = _validate_lines(db, payload.lines)
    document = StockDocument(
        doc_no=_next_doc_no(db, doc_type, doc_date),
        doc_type=doc_type,
        doc_date=doc_date,
        supplier_id=getattr(payload, "supplier_id", None),
        customer_id=getattr(payload, "customer_id", None),
        crop_cycle_id=payload.crop_cycle_id,
        reference_no=payload.reference_no,
        note_encrypted=encrypt_text(payload.note).encode("ascii") if payload.note else None,
        status="posted",
        created_by=created_by,
    )
    db.add(document)
    db.flush()
    if getattr(payload, "purpose", None) is not None:
        set_document_purpose(db, document.id, payload.purpose)
    movement_type = "receipt" if doc_type == "inbound" else "shipment"
    for line in lines:
        db.add(StockDocumentLine(
            document_id=document.id,
            line_no=line["line_no"],
            product_id=line["product"].id,
            quantity=float(line["quantity"]),
            unit=line["unit"],
            unit_price_encrypted=encrypt_number(line["unit_price"]).encode("ascii") if line["unit_price"] is not None else None,
            line_amount_encrypted=encrypt_number(line["line_amount"]).encode("ascii") if line["line_amount"] is not None else None,
        ))
    db.flush()
    for line in lines:
        base_quantity = line["base_quantity"]
        if base_quantity is None:
            continue
        delta = base_quantity if doc_type == "inbound" else -base_quantity
        record_movement(
            db,
            line["product"].id,
            delta,
            line["product"].unit,
            movement_type,
            source_type=STOCK_DOCUMENT,
            source_id=document.id,
            occurred_at=start_of_day(doc_date),
        )
    db.flush()
    if doc_type == "outbound":
        balances = on_hand_grouped(db, sorted({line["product"].id for line in lines if line["base_quantity"] is not None}))
        warnings.extend(f"negative_balance:{product_id}" for product_id, balance in balances.items() if balance < 0)
        warnings.extend(expired_lot_warnings(db, document.id, sorted(balances)))
    return document, sorted(set(warnings))


def set_document_purpose(db: Session, document_id: int, purpose: str, order_id: int | None = None) -> None:
    db.add(StockDocumentPurpose(document_id=document_id, purpose=purpose, order_id=order_id))
    db.flush()


def document_purpose(db: Session, document: StockDocument) -> tuple[str | None, SalesOrder | None]:
    """Purpose and order of an outbound document; None for documents issued before purposes existed."""
    row = db.scalar(select(StockDocumentPurpose).where(StockDocumentPurpose.document_id == document.id))
    if row is not None:
        return row.purpose, db.get(SalesOrder, row.order_id) if row.order_id is not None else None
    order = db.scalar(
        select(SalesOrder)
        .join(SalesOrderLine, SalesOrderLine.order_id == SalesOrder.id)
        .join(SalesOrderDelivery, SalesOrderDelivery.line_id == SalesOrderLine.id)
        .where(SalesOrderDelivery.document_id == document.id)
        .limit(1)
    )
    return ("order", order) if order is not None else (None, None)


def last_unit_prices(db: Session, doc_type: str) -> list[dict]:
    """Most recent readable price of each product and unit."""
    statement = (
        select(StockDocumentLine)
        .join(StockDocument, StockDocument.id == StockDocumentLine.document_id)
        .outerjoin(StockDocumentPurpose, StockDocumentPurpose.document_id == StockDocument.id)
        .where(
            StockDocument.doc_type == doc_type,
            StockDocument.status == "posted",
            StockDocumentLine.unit_price_encrypted.is_not(None),
            func.coalesce(StockDocumentPurpose.purpose, "sale") != "other",
        )
        .order_by(StockDocument.doc_date.desc(), StockDocument.id.desc(), StockDocumentLine.line_no.desc())
    )
    prices: dict[tuple[int, str], dict] = {}
    for line in db.scalars(statement):
        key = (line.product_id, line.unit)
        if key in prices:
            continue
        price = safe_decrypt_number(
            line.unit_price_encrypted, table="stock_document_lines", row_id=line.id, field="unit_price"
        )
        if not price.decrypt_failed:
            prices[key] = {"product_id": line.product_id, "unit": line.unit, "unit_price": price.value}
    return list(prices.values())


def void_stock_document(db: Session, document: StockDocument, reason: str | None) -> None:
    if document.status == "void" or document.voided_at is not None:
        raise ValueError("Document is already void")
    active_count = db.scalar(select(func.count()).select_from(StockMovement).where(
        StockMovement.source_type == STOCK_DOCUMENT,
        StockMovement.source_id == document.id,
        StockMovement.voided_at.is_(None),
    )) or 0
    document.status = "void"
    document.voided_at = utc_now()
    document.void_reason_encrypted = encrypt_text(reason).encode("ascii") if reason else None
    db.flush()
    voided_count = void_source_movements(db, STOCK_DOCUMENT, document.id)
    if voided_count != active_count:
        raise RuntimeError("Stock document movement ledger is inconsistent")
    db.flush()


def present_stock_document(db: Session, document: StockDocument, role, warnings: list[str] | None = None):
    lines = db.scalars(
        select(StockDocumentLine).where(StockDocumentLine.document_id == document.id).order_by(StockDocumentLine.line_no)
    ).all()
    presented_lines = []
    aggregate_total = Decimal("0")
    aggregate_failed = False
    decrypt_failed = False
    product_ids = sorted({line.product_id for line in lines})
    products = {p.id: p for p in db.scalars(select(Product).where(Product.id.in_(product_ids))).all()} if product_ids else {}
    for line in lines:
        product = products.get(line.product_id)
        product_name = present_text_safe(
            product.name_encrypted if product else None,
            role,
            table="products",
            row_id=product.id if product else line.product_id,
            field="name",
        )
        unit_price = present_number_safe(
            line.unit_price_encrypted, role, table="stock_document_lines", row_id=line.id, field="unit_price"
        )
        line_amount = present_number_safe(
            line.line_amount_encrypted, role, table="stock_document_lines", row_id=line.id, field="line_amount"
        )
        total_result = safe_decrypt_number(
            line.line_amount_encrypted, table="stock_document_lines", row_id=line.id, field="line_amount"
        ) if line.line_amount_encrypted else None
        if total_result and total_result.decrypt_failed:
            aggregate_failed = True
        elif total_result:
            aggregate_total += total_result.value
        decrypt_failed = decrypt_failed or product_name.decrypt_failed or unit_price.decrypt_failed or line_amount.decrypt_failed
        presented_lines.append({
            "id": line.id,
            "line_no": line.line_no,
            "product_id": line.product_id,
            "product_name": product_name.value,
            "quantity": line.quantity,
            "unit": line.unit,
            "unit_price": unit_price.value if line.unit_price_encrypted else None,
            "line_amount": line_amount.value if line.line_amount_encrypted else None,
            "is_masked": role.value != "owner",
            "decrypt_failed": product_name.decrypt_failed or unit_price.decrypt_failed or line_amount.decrypt_failed,
        })
    note = present_text_safe(document.note_encrypted, role, table="stock_documents", row_id=document.id, field="note")
    reason = present_text_safe(document.void_reason_encrypted, role, table="stock_documents", row_id=document.id, field="void_reason")
    supplier = db.get(Supplier, document.supplier_id) if document.supplier_id is not None else None
    customer = db.get(Customer, document.customer_id) if document.customer_id is not None else None
    supplier_name = present_text_safe(supplier.name_encrypted, role, table="suppliers", row_id=supplier.id, field="name") if supplier else None
    customer_name = present_text_safe(customer.name_encrypted, role, table="customers", row_id=customer.id, field="name") if customer else None
    if supplier_name:
        decrypt_failed = decrypt_failed or supplier_name.decrypt_failed
    if customer_name:
        decrypt_failed = decrypt_failed or customer_name.decrypt_failed
    decrypt_failed = decrypt_failed or note.decrypt_failed or reason.decrypt_failed
    total_amount = None if aggregate_failed or not any(line.line_amount_encrypted for line in lines) else present_aggregate(aggregate_total, role)
    if document.doc_type == "outbound" and document.status == "posted" and warnings is None:
        balances = on_hand_grouped(db, product_ids)
        warnings = [f"negative_balance:{product_id}" for product_id, balance in balances.items() if balance < 0]
        warnings.extend(expired_lot_warnings(db, document.id, product_ids))
    purpose, order = document_purpose(db, document) if document.doc_type == "outbound" else (None, None)
    cycle = db.get(CropCycle, document.crop_cycle_id) if document.crop_cycle_id is not None else None
    return {
        "crop_cycle_label": f"โต๊ะ {cycle.table.table_number} · {cycle.crop_type.name} · {cycle.cycle_code}" if cycle else None,
        "purpose": purpose,
        "order_id": order.id if order else None,
        "order_no": order.order_no if order else None,
        "finance_recorded": document_finance_entry(db, document.id) is not None,
        "id": document.id,
        "doc_no": document.doc_no,
        "doc_type": document.doc_type,
        "doc_date": document.doc_date,
        "supplier_id": document.supplier_id,
        "supplier_name": supplier_name.value if supplier_name else None,
        "customer_id": document.customer_id,
        "customer_name": customer_name.value if customer_name else None,
        "crop_cycle_id": document.crop_cycle_id,
        "reference_no": document.reference_no,
        "note": note.value if document.note_encrypted else None,
        "void_reason": reason.value if document.void_reason_encrypted else None,
        "total_amount": total_amount,
        "status": document.status,
        "voided_at": document.voided_at,
        "lines": presented_lines,
        "warnings": warnings or [],
        "is_masked": role.value != "owner",
        "decrypt_failed": decrypt_failed or aggregate_failed,
        "created_at": document.created_at,
        "updated_at": document.updated_at,
    }

