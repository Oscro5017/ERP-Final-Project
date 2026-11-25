from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import FinanceEntry, Task
from .finance_entries import _now_utc
from .secure_fields import decrypt_number, encrypt_number, encrypt_text, safe_decrypt_number
from .source_types import TASK

_CENT = Decimal("0.01")


def _task_cost(token: bytes | None) -> Decimal | None:
    return decrypt_number(token) if token else None


def sync_task_finance(db: Session, task: Task, created_by: int | None = None) -> FinanceEntry | None:
    entries = db.scalars(select(FinanceEntry).where(
        FinanceEntry.source_type == TASK,
        FinanceEntry.source_id == task.id,
        FinanceEntry.is_auto.is_(True),
        FinanceEntry.status == "posted",
    ).order_by(FinanceEntry.id)).all()

    labor_cost = _task_cost(task.labor_cost_encrypted)
    extra_cost = _task_cost(task.extra_cost_encrypted)
    has_cost_data = labor_cost is not None or extra_cost is not None or task.worker_count is not None
    if task.deleted_at is not None or task.status != "done" or not has_cost_data:
        _void(entries, "Task is no longer financially complete")
        return None

    amount = ((labor_cost or Decimal("0")) + (extra_cost or Decimal("0"))).quantize(_CENT, rounding=ROUND_HALF_UP)
    if len(entries) == 1:
        current = entries[0]
        decrypted = safe_decrypt_number(current.amount_encrypted, table="finance_entries", row_id=current.id, field="amount")
        same_amount = not decrypted.decrypt_failed and decrypted.value == amount
        if same_amount and current.crop_cycle_id == task.cycle_id and current.entry_date == task.due_date:
            return current
    _void(entries, "Task financial values updated")
    entry = FinanceEntry(
        entry_date=task.due_date,
        direction="expense",
        category="labor",
        amount_encrypted=encrypt_number(amount).encode("ascii"),
        source_type=TASK,
        source_id=task.id,
        crop_cycle_id=task.cycle_id,
        is_auto=True,
        status="posted",
        created_by=created_by,
    )
    db.add(entry)
    db.flush()
    return entry


def void_task_finance(db: Session, task_id: int, reason: str = "Task removed") -> int:
    entries = db.scalars(select(FinanceEntry).where(
        FinanceEntry.source_type == TASK,
        FinanceEntry.source_id == task_id,
        FinanceEntry.is_auto.is_(True),
        FinanceEntry.status == "posted",
    )).all()
    _void(entries, reason)
    return len(entries)


def _void(entries: list[FinanceEntry], reason: str) -> None:
    for entry in entries:
        entry.status = "void"
        entry.voided_at = _now_utc()
        entry.void_reason_encrypted = encrypt_text(reason).encode("ascii")
