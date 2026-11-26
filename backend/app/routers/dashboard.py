from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import CropCycle, CycleStatus, FinanceEntry, Product, Role, StockMovement, Task, User
from ..security import get_current_user
from ..services.secure_fields import present_aggregate, safe_decrypt_number

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
_BANGKOK = ZoneInfo("Asia/Bangkok")
_MAX_FINANCE_ROWS = 10_000


def _today_bangkok() -> date:
    return datetime.now(_BANGKOK).date()


@router.get("/summary")
def dashboard_summary(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    today = _today_bangkok()
    month_start = today.replace(day=1)
    next_month = date(today.year + 1, 1, 1) if today.month == 12 else date(today.year, today.month + 1, 1)

    balances = select(
        StockMovement.product_id.label("product_id"),
        func.sum(StockMovement.quantity_delta).label("quantity"),
    ).where(StockMovement.voided_at.is_(None)).group_by(StockMovement.product_id).subquery()
    product_count, negative_count = db.execute(select(
        func.count(Product.id),
        func.coalesce(func.sum(case((func.coalesce(balances.c.quantity, 0) < 0, 1), else_=0)), 0),
    ).select_from(Product).outerjoin(balances, balances.c.product_id == Product.id).where(Product.deleted_at.is_(None))).one()

    cycle_rows = db.execute(select(CropCycle.status, func.count(CropCycle.id)).where(
        CropCycle.deleted_at.is_(None)
    ).group_by(CropCycle.status)).all()
    cycles_by_status = {status.value: 0 for status in CycleStatus}
    cycles_by_status.update({status.value if hasattr(status, "value") else status: count for status, count in cycle_rows})

    due_today, overdue = db.execute(select(
        func.coalesce(func.sum(case((Task.due_date == today, 1), else_=0)), 0),
        func.coalesce(func.sum(case((Task.due_date < today, 1), else_=0)), 0),
    ).where(
        Task.deleted_at.is_(None), Task.status == "pending"
    )).one()

    finance_rows = db.execute(select(FinanceEntry.id, FinanceEntry.direction, FinanceEntry.amount_encrypted).where(
        FinanceEntry.status == "posted",
        FinanceEntry.entry_date >= month_start,
        FinanceEntry.entry_date < next_month,
    ).order_by(FinanceEntry.entry_date, FinanceEntry.id).limit(_MAX_FINANCE_ROWS + 1)).all()
    truncated = len(finance_rows) > _MAX_FINANCE_ROWS
    income = expense = 0
    skipped = 0
    for entry_id, direction, encrypted_amount in finance_rows[:_MAX_FINANCE_ROWS]:
        result = safe_decrypt_number(encrypted_amount, table="finance_entries", row_id=entry_id, field="amount")
        if result.decrypt_failed or result.value is None:
            skipped += 1
            continue
        if direction == "income":
            income += result.value
        elif direction == "expense":
            expense += result.value
    profit = income - expense
    return {
        "as_of": today,
        "product_count": int(product_count or 0),
        "negative_product_count": int(negative_count or 0),
        "crop_cycles_by_status": cycles_by_status,
        "tasks_due_today": int(due_today or 0),
        "tasks_overdue": int(overdue or 0),
        "finance_month": {
            "from": month_start,
            "to": today,
            "income": present_aggregate(income, user.role),
            "expense": present_aggregate(expense, user.role),
            "profit": present_aggregate(profit, user.role),
            "skipped_decrypt_failed": skipped,
            "truncated": truncated,
        },
    }
