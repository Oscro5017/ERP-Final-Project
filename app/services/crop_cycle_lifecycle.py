from datetime import UTC, datetime

from sqlalchemy.orm import Session

from ..models import CropCycle, CropCycleStatusLog
from .task_generator import sync_crop_cycle_tasks


def sync_crop_cycle_lifecycle(db: Session, cycle: CropCycle, previous_status=None, created: bool = False) -> None:
    if created or previous_status != cycle.status:
        db.add(CropCycleStatusLog(
            cycle_id=cycle.id,
            from_status=previous_status.value if previous_status else None,
            to_status=cycle.status.value if hasattr(cycle.status, "value") else cycle.status,
            changed_at=datetime.now(UTC),
        ))
    sync_crop_cycle_tasks(db, cycle)