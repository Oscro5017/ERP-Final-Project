import logging
from datetime import date, timedelta

from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from .config import Settings, get_settings
from .models import Batch, CropCycle, CropCycleStatusLog, CropType, CycleStatus, Role, Table, User
from .security import hash_password, verify_password


logger = logging.getLogger(__name__)


def validate_production_default_passwords(db: Session, settings: Settings) -> None:
    if settings.app_env.strip().lower() != "production":
        return

    bind = db.get_bind()
    if not inspect(bind).has_table(User.__tablename__):
        return

    development_defaults = ("owner123", "developer123")
    users = db.scalars(select(User)).all()
    for user in users:
        if any(verify_password(password, user.password_hash) for password in development_defaults):
            raise RuntimeError(
                f"Production startup blocked: account '{user.username}' still uses a development default password. Change it before startup."
            )


def seed_database(db: Session, settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    if db.scalar(select(User).where(User.username == "owner")):
        return
    production = settings.app_env.strip().lower() == "production"
    initial_passwords = {
        "owner": settings.initial_owner_password or (None if production else "owner123"),
        "developer": settings.initial_developer_password or (None if production else "developer123"),
    }
    for username, role in (("owner", Role.owner), ("developer", Role.developer)):
        if db.scalar(select(User).where(User.username == username)):
            continue
        password = initial_passwords[username]
        if not password:
            logger.error("Initial %s account was not created: its initial password is not configured.", username)
            continue
        db.add(User(username=username, password_hash=hash_password(password), role=role))

    if db.scalar(select(Table.id).limit(1)):
        db.commit()
        return

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
