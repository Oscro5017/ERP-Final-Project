from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import FinanceEntry, StockDocument, StockDocumentLine
from .secure_fields import decrypt_number, encrypt_number, encrypt_text
from .source_types import STOCK_DOCUMENT

_CENT = Decimal("0.01")
_BANGKOK = ZoneInfo("Asia/Bangkok")


def _now_utc() -> datetime:
    return datetime.now(UTC)


def finance_today() -> date:
    return datetime.now(_BANGKOK).date()


def create_auto_finance_for_document(db: Session, document: StockDocument, created_by: int | None = None) -> FinanceEntry | None:
    existing = db.scalar(select(FinanceEntry).where(
        FinanceEntry.source_type == STOCK_DOCUMENT,
        FinanceEntry.source_id == document.id,
        FinanceEntry.is_auto.is_(True),
        FinanceEntry.status == "posted",
    ))
    if existing is not None:
        return existing
    lines = db.scalars(select(StockDocumentLine).where(
        StockDocumentLine.document_id == document.id
    ).order_by(StockDocumentLine.line_no)).all()
    priced_lines = [line for line in lines if line.line_amount_encrypted is not None]
    if not priced_lines:
        return None
    amount = sum((decrypt_number(line.line_amount_encrypted) for line in priced_lines), Decimal("0"))
    amount = amount.quantize(_CENT, rounding=ROUND_HALF_UP)
    if amount <= 0:
        return None
    is_outbound = document.doc_type == "outbound"
    entry = FinanceEntry(
        entry_date=document.doc_date,
        direction="income" if is_outbound else "expense",
        category="sale" if is_outbound else "purchase",
        amount_encrypted=encrypt_number(amount).encode("ascii"),
        description_encrypted=None,
        source_type=STOCK_DOCUMENT,
        source_id=document.id,
        crop_cycle_id=document.crop_cycle_id,
        customer_id=document.customer_id,
        supplier_id=document.supplier_id,
        is_auto=True,
        status="posted",
        created_by=created_by,
    )
    db.add(entry)
    db.flush()
    return entry


def void_auto_finance_for_document(db: Session, document: StockDocument, reason: str | None = None) -> int:
    entries = db.scalars(select(FinanceEntry).where(
        FinanceEntry.source_type == STOCK_DOCUMENT,
        FinanceEntry.source_id == document.id,
        FinanceEntry.is_auto.is_(True),
        FinanceEntry.status == "posted",
    )).all()
    for entry in entries:
        entry.status = "void"
        entry.voided_at = _now_utc()
        entry.void_reason_encrypted = encrypt_text(reason).encode("ascii") if reason else None
    if entries:
        db.flush()
    return len(entries)


def validate_manual_amount(value) -> Decimal:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("Invalid amount") from exc
    if not amount.is_finite() or amount <= 0:
        raise ValueError("Amount must be greater than zero")
    return amount.quantize(_CENT, rounding=ROUND_HALF_UP)
