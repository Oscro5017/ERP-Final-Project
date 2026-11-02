from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Batch, CropCycle, CropCycleStatusLog, CropType, CycleStatus, Role, Table, User
from .security import hash_password


def seed_database(db: Session) -> None:
    if db.scalar(select(User).where(User.username == "owner")):
        return
    db.add_all([
        User(username="owner", password_hash=hash_password("owner123"), role=Role.owner),
        User(username="developer", password_hash=hash_password("developer123"), role=Role.developer),
    ])
    db.add_all([Table(table_number=number) for number in range(1, 50)])
    today = date.today()
    db.add_all([Batch(batch_number=number, start_date=today + timedelta(days=(number - 1) * 7), week_offset=number - 1) for number in range(1, 9)])
    crop_types = [
        CropType(name="Green Oak", nursery_days=14, growth_days=28),
        CropType(name="Red Oak", nursery_days=14, growth_days=28),
        CropType(name="Frilly", nursery_days=14, growth_days=28),
    ]
    db.add_all(crop_types)
    db.flush()
    cycles = [
        CropCycle(table_id=number, batch_id=number, crop_type_id=crop_types[(number - 1) % 3].id,
                  nursery_start=today + timedelta(days=(number - 1) * 7), status=CycleStatus.nursery)
        for number in range(1, 9)
    ]
    db.add_all(cycles)
    db.flush()
    db.add_all([
        CropCycleStatusLog(cycle_id=cycle.id, from_status=None, to_status=cycle.status.value)
        for cycle in cycles
    ])
    db.commit()
