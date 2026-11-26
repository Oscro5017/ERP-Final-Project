from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import CropCycleOption

OPTION_FIELDS = {"create_tasks", "record_harvest_stock"}


def cycle_option(db: Session, cycle_id: int, field: str) -> bool:
    row = db.scalar(select(CropCycleOption).where(CropCycleOption.cycle_id == cycle_id))
    return True if row is None else bool(getattr(row, field))


def save_cycle_options(db: Session, cycle_id: int, values: dict) -> None:
    """Remember explicit choices only; None leaves the current choice alone."""
    values = {field: value for field, value in values.items() if field in OPTION_FIELDS and value is not None}
    if not values:
        return
    row = db.scalar(select(CropCycleOption).where(CropCycleOption.cycle_id == cycle_id))
    if row is None:
        if all(values.values()):
            return
        row = CropCycleOption(cycle_id=cycle_id, create_tasks=True, record_harvest_stock=True)
        db.add(row)
    for field, value in values.items():
        setattr(row, field, value)
    db.flush()
