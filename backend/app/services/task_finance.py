"""Labor and other costs of a finished activity become expense entries.

An activity that covers several crop cycles splits its cost by each cycle's share,
so the cost per cycle stays right. Without a crop cycle the cost is one farm expense.
"""
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Activity, ActivityTarget, FinanceEntry
from .finance_entries import _now_utc
from .secure_fields import decrypt_number, encrypt_number, encrypt_text, safe_decrypt_number
from .source_types import TASK

_CENT = Decimal("0.01")


def _task_cost(token: bytes | None) -> Decimal | None:
    return decrypt_number(token) if token else None


def split_by_share(amount: Decimal, shares: list[tuple[int, float]]) -> list[tuple[int, Decimal]]:
    """Split an amount in cents by share; the last part takes the rounding remainder."""
    total_share = sum(share for _key, share in shares)
    parts = []
    remaining = amount
    for index, (key, share) in enumerate(shares):
        if index == len(shares) - 1:
            part = remaining
        else:
            part = (amount * Decimal(str(share)) / Decimal(str(total_share))).quantize(_CENT, rounding=ROUND_HALF_UP)
            remaining -= part
        parts.append((key, part))
    return parts


def _cycle_shares(db: Session, task: Activity) -> list[tuple[int, float]]:
    targets = db.scalars(select(ActivityTarget).where(
        ActivityTarget.activity_id == task.id,
        ActivityTarget.crop_cycle_id.is_not(None),
    ).order_by(ActivityTarget.crop_cycle_id)).all()
    shares = [(target.crop_cycle_id, target.share if target.share and target.share > 0 else 1.0) for target in targets]
    if not shares and task.cycle_id is not None:
        shares = [(task.cycle_id, 1.0)]
    return shares


def sync_task_finance(db: Session, task: Activity, created_by: int | None = None) -> list[FinanceEntry]:
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
        return []

    amount = ((labor_cost or Decimal("0")) + (extra_cost or Decimal("0"))).quantize(_CENT, rounding=ROUND_HALF_UP)
    entry_date = task.done_on or task.planned_date
    shares = _cycle_shares(db, task)
    wanted = split_by_share(amount, shares) if shares else [(None, amount)]

    current = []
    for entry in entries:
        decrypted = safe_decrypt_number(entry.amount_encrypted, table="finance_entries", row_id=entry.id, field="amount")
        current.append((entry.crop_cycle_id, None if decrypted.decrypt_failed else decrypted.value, entry.entry_date))
    def by_cycle(row):
        return (row[0] is None, row[0] or 0)

    if sorted(current, key=by_cycle) == sorted([(cycle_id, part, entry_date) for cycle_id, part in wanted], key=by_cycle):
        return entries

    _void(entries, "Task financial values updated")
    created = []
    for cycle_id, part in wanted:
        entry = FinanceEntry(
            entry_date=entry_date,
            direction="expense",
            category="labor",
            amount_encrypted=encrypt_number(part).encode("ascii"),
            source_type=TASK,
            source_id=task.id,
            crop_cycle_id=cycle_id,
            is_auto=True,
            status="posted",
            created_by=created_by,
        )
        db.add(entry)
        created.append(entry)
    db.flush()
    return created


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
