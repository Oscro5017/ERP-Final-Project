"""How much of each grow table is in use, and whether it is ready to plant.

A table holds up to ``capacity_plants`` plants and may grow several crops at once.
A cycle takes up its plant count from sowing until the table is cleaned after its
harvest; a cycle without a plant count is assumed to fill the whole table.
"""
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Activity, ActivityKind, ActivityTarget, CropCycle, CycleStatus, Table

READY = "ready"  # ว่างพร้อมปลูก
NEEDS_CLEANING = "needs_cleaning"  # รอล้างโต๊ะ
PARTIAL = "partial"  # ว่างบางส่วน
FULL = "full"  # เต็ม


@dataclass
class CycleSpace:
    cycle: CropCycle
    plants: int
    awaiting_cleanup: bool


@dataclass
class TableSpace:
    table: Table
    used: int = 0
    cycles: list[CycleSpace] = field(default_factory=list)

    @property
    def capacity(self) -> int:
        return self.table.capacity_plants

    @property
    def free(self) -> int:
        return max(0, self.capacity - self.used)

    @property
    def state(self) -> str:
        if not self.cycles:
            return READY
        if all(space.awaiting_cleanup for space in self.cycles):
            return NEEDS_CLEANING
        return PARTIAL if self.free > 0 else FULL


def _cleaned_cycles(db: Session, cycles: list[CropCycle]) -> set[int]:
    """Harvested cycles whose table was cleaned afterwards (for that cycle or the whole table)."""
    harvested = [cycle for cycle in cycles if cycle.status == CycleStatus.harvested]
    if not harvested:
        return set()
    rows = db.execute(
        select(ActivityTarget.crop_cycle_id, ActivityTarget.table_id, Activity.done_on)
        .join(Activity, Activity.id == ActivityTarget.activity_id)
        .where(
            Activity.kind == ActivityKind.cleanup.value,
            Activity.status == "done",
            Activity.deleted_at.is_(None),
        )
    ).all()
    by_cycle = {cycle_id for cycle_id, _table_id, _done_on in rows if cycle_id is not None}
    table_cleanings: dict[int, list[date]] = {}
    for cycle_id, table_id, done_on in rows:
        if cycle_id is None and table_id is not None and done_on is not None:
            table_cleanings.setdefault(table_id, []).append(done_on)
    cleaned = set()
    for cycle in harvested:
        if cycle.id in by_cycle:
            cleaned.add(cycle.id)
            continue
        finished = cycle.harvest_date or cycle.nursery_start
        if any(day >= finished for day in table_cleanings.get(cycle.table_id, [])):
            cleaned.add(cycle.id)
    return cleaned


def table_spaces(db: Session) -> list[TableSpace]:
    tables = db.scalars(select(Table).order_by(Table.table_number)).all()
    spaces = {table.id: TableSpace(table) for table in tables}
    cycles = db.scalars(select(CropCycle).where(CropCycle.deleted_at.is_(None)).order_by(CropCycle.nursery_start, CropCycle.id)).all()
    cleaned = _cleaned_cycles(db, cycles)
    for cycle in cycles:
        space = spaces.get(cycle.table_id)
        if space is None or cycle.id in cleaned:
            continue
        if cycle.plant_count is not None:
            plants = cycle.plant_count
        elif cycle.seed_count:
            plants = min(cycle.seed_count, space.capacity)  # seedlings expected on this table
        else:
            plants = space.capacity
        space.cycles.append(CycleSpace(cycle, plants, cycle.status == CycleStatus.harvested))
        space.used += plants
    return list(spaces.values())


def free_table_spaces(db: Session) -> list[TableSpace]:
    """Tables with room for more plants, emptiest first by table number."""
    return [space for space in table_spaces(db) if space.free > 0]
