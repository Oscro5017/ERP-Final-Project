"""Phase 3 step 3: production stages, seeds, plant counts and harvests over several days."""
from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.migrations import migrate_production_records
from app.models import (
    Activity, AutomationPreference, Batch, ChangeNote, CropCycle, CropType, CycleStatus, HarvestEntry, LotExpiryOverride,
    Product, Role, StockMovement, StockWaste, Table, User,
)
from app.security import get_current_user
from app.services.crop_production import advance_ready_cycles, timing_note
from app.services.products_stock import on_hand
from app.services.secure_fields import decrypt_text, encrypt_text, hash_catalog_name
from app.services.source_types import ACTIVITY, HARVEST_ENTRY

START = date(2026, 11, 1)


def make_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False)
    with Session() as db:
        db.add_all([
            User(id=1, username="owner", password_hash="x", role=Role.owner),
            Table(id=1, table_number=1),
            Batch(id=1, batch_number=1, start_date=date(2026, 1, 1)),
            Product(id=1, category="vegetable", name_encrypted=encrypt_text("คะน้า").encode(), name_hash=hash_catalog_name("คะน้า"), unit="kg"),
            Product(id=2, category="seed", name_encrypted=encrypt_text("เมล็ดคะน้า").encode(), name_hash=hash_catalog_name("เมล็ดคะน้า"), unit="เมล็ด"),
        ])
        db.flush()
        db.add(CropType(id=1, name="คะน้า", nursery_days=10, growth_days=30, product_id=1, seed_product_id=2))
        db.add(StockMovement(product_id=2, quantity_delta=800, movement_type="receipt", occurred_at=datetime(2026, 10, 1)))
        db.commit()
    return engine, Session


@pytest.fixture
def env():
    _, Session = make_db()

    def override_db():
        with Session() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: User(id=1, username="owner", password_hash="x", role=Role.owner)
    client = TestClient(app)
    client.Session = Session
    yield client
    app.dependency_overrides.clear()


def new_cycle(client, **extra):
    body = {"table_id": 1, "batch_id": 1, "crop_type_id": 1, "nursery_start": START.isoformat(), **extra}
    response = client.post("/crop-cycles", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def kinds(client, cycle_id):
    return {(a["kind"], a["status"]) for a in client.get(f"/activities?cycle_id={cycle_id}").json()}


# Seeds and expected dates --------------------------------------------------------

def test_sowing_records_a_nursery_activity_that_takes_the_seeds(env):
    cycle = new_cycle(env, seed_count=220)
    assert (cycle["expected_transplant_on"], cycle["expected_ready_on"]) == ("2026-11-11", "2026-12-11")
    [nursery] = env.get(f"/activities?cycle_id={cycle['id']}&kind=nursery").json()
    assert (nursery["status"], nursery["done_on"]) == ("done", "2026-11-01")
    assert nursery["items"][0]["quantity"] == "220" and nursery["items"][0]["unit"] == "เมล็ด"
    with env.Session() as db:
        assert on_hand(db, 2) == 580

    env.patch(f"/crop-cycles/{cycle['id']}", json={"seed_count": 200, "reason": "นับใหม่"})
    with env.Session() as db:
        assert on_hand(db, 2) == 600
    env.patch(f"/crop-cycles/{cycle['id']}", json={"seed_count": None})
    assert env.get(f"/activities?cycle_id={cycle['id']}&kind=nursery").json() == []
    with env.Session() as db:
        assert on_hand(db, 2) == 800


def test_seeds_can_be_recorded_without_taking_them_from_stock(env):
    cycle = new_cycle(env, seed_count=100, deduct_seeds=False)
    [nursery] = env.get(f"/activities?cycle_id={cycle['id']}&kind=nursery").json()
    assert nursery["items"] == []
    with env.Session() as db:
        assert on_hand(db, 2) == 800


def test_new_stage_lengths_move_growing_cycles_and_their_reminders(env):
    cycle = new_cycle(env)
    assert env.patch("/crop-types/1", json={"nursery_days": 12, "growth_days": 35}).status_code == 200
    moved = [c for c in env.get("/crop-cycles").json() if c["id"] == cycle["id"]][0]
    assert (moved["expected_transplant_on"], moved["expected_ready_on"]) == ("2026-11-13", "2026-12-18")
    [transplant] = env.get(f"/activities?cycle_id={cycle['id']}&kind=transplant").json()
    assert transplant["planned_date"] == "2026-11-13"


# Stage changes ----------------------------------------------------------------

def test_transplanting_early_records_plants_and_a_timing_note(env):
    cycle = new_cycle(env)
    response = env.post(f"/crop-cycles/{cycle['id']}/status", json={
        "status": "bushed", "on_date": "2026-11-09", "plant_count": 180, "reason": "ต้นกล้าแข็งแรงเร็ว",
    })
    body = response.json()
    assert (body["status"], body["transplant_date"], body["plant_count"]) == ("bushed", "2026-11-09", 180)
    assert body["expected_ready_on"] == "2026-12-09"
    status_note = [c for c in env.get(f"/crop-cycles/{cycle['id']}/changes").json() if c["field"] == "status"][0]
    assert (status_note["old_value"], status_note["new_value"]) == ("nursery", "bushed")
    assert status_note["reason"] == "ต้นกล้าแข็งแรงเร็ว"
    assert status_note["auto_note"] == "ลงปลูกก่อนวันที่คำนวณ 2 วัน"
    [transplant] = env.get(f"/activities?cycle_id={cycle['id']}&kind=transplant").json()
    assert (transplant["status"], transplant["done_on"]) == ("done", "2026-11-09")
    assert ("harvest", "pending") in kinds(env, cycle["id"])


def test_timing_note_wording():
    assert timing_note("bushed", date(2026, 11, 14), date(2026, 11, 11)) == "ลงปลูกหลังวันที่คำนวณ 3 วัน"
    assert timing_note("bushed", date(2026, 11, 11), date(2026, 11, 11)) is None


def test_starting_the_harvest_needs_a_quantity(env):
    cycle = new_cycle(env)
    assert env.post(f"/crop-cycles/{cycle['id']}/status", json={"status": "harvesting"}).status_code == 422


# Harvests over several days --------------------------------------------------------

def test_partial_harvests_add_stock_lots_and_a_final_one_closes_the_cycle(env):
    cycle = new_cycle(env)
    env.post(f"/crop-cycles/{cycle['id']}/status", json={"status": "bushed", "on_date": "2026-11-11", "plant_count": 190})
    first = env.post(f"/crop-cycles/{cycle['id']}/harvests", json={"harvested_on": "2026-12-10", "quantity_kg": 4})
    assert first.status_code == 201, first.text
    assert (first.json()["status"], first.json()["harvest_quantity_kg"]) == ("harvesting", 4)
    assert ("harvest", "in_progress") in kinds(env, cycle["id"])

    final = env.post(f"/crop-cycles/{cycle['id']}/harvests", json={"harvested_on": "2026-12-12", "quantity_kg": 2.5, "final": True})
    body = final.json()
    assert (body["status"], body["harvest_quantity_kg"], body["harvest_date"]) == ("harvested", 6.5, "2026-12-12")
    assert {("harvest", "done"), ("cleanup", "pending")} <= kinds(env, cycle["id"])
    with env.Session() as db:
        receipts = db.scalars(select(StockMovement).where(StockMovement.source_type == HARVEST_ENTRY)).all()
        assert sorted((m.quantity_delta, m.occurred_at.date()) for m in receipts) == [
            (2.5, date(2026, 12, 11)), (4.0, date(2026, 12, 9)),  # Bangkok midnight in UTC
        ]
        assert on_hand(db, 1) == 6.5

    assert env.post(f"/crop-cycles/{cycle['id']}/harvests", json={"quantity_kg": 1}).status_code == 422
    entries = env.get(f"/crop-cycles/{cycle['id']}/harvests").json()
    assert env.delete(f"/crop-cycles/harvests/{entries[0]['id']}").status_code == 204
    with env.Session() as db:
        assert db.get(CropCycle, cycle["id"]).harvest_quantity_kg == 2.5
        assert on_hand(db, 1) == 2.5


def test_single_figure_harvest_edit_is_refused_after_several_picks(env):
    cycle = new_cycle(env)
    env.post(f"/crop-cycles/{cycle['id']}/harvests", json={"harvested_on": "2026-12-10", "quantity_kg": 4})
    env.post(f"/crop-cycles/{cycle['id']}/harvests", json={"harvested_on": "2026-12-11", "quantity_kg": 3})
    assert env.patch(f"/crop-cycles/{cycle['id']}", json={"harvest_quantity_kg": 9}).status_code == 422


def test_each_pick_is_its_own_fresh_lot(env):
    assert env.put("/freshness/products/1", json={"shelf_life_days": 5, "warn_days": 1}).status_code == 200
    cycle = new_cycle(env)
    env.post(f"/crop-cycles/{cycle['id']}/harvests", json={"harvested_on": "2026-12-10", "quantity_kg": 4})
    env.post(f"/crop-cycles/{cycle['id']}/harvests", json={"harvested_on": "2026-12-12", "quantity_kg": 2})
    lots = [lot for lot in env.get("/freshness/lots").json()["items"] if lot["product_id"] == 1]
    assert sorted((lot["received_on"], lot["lot_key"].startswith("harvest-entry-")) for lot in lots) == [
        ("2026-12-10", True), ("2026-12-12", True),
    ]


# The daily stage job ----------------------------------------------------------------

def test_cycles_become_ready_on_their_expected_date_unless_the_owner_does_it_by_hand(env):
    cycle = new_cycle(env)
    env.post(f"/crop-cycles/{cycle['id']}/status", json={"status": "bushed", "on_date": "2026-11-11"})
    with env.Session() as db:
        assert advance_ready_cycles(db, date(2026, 12, 10)) == 0
        assert advance_ready_cycles(db, date(2026, 12, 11)) == 1
        db.commit()
        assert db.get(CropCycle, cycle["id"]).status == CycleStatus.ready_to_harvest
        note = db.scalar(select(ChangeNote).where(ChangeNote.field == "status").order_by(ChangeNote.id.desc()))
        assert decrypt_text(note.auto_note_encrypted) == "ระบบเปลี่ยนตามวันที่คำนวณ"

    second = new_cycle(env)
    env.post(f"/crop-cycles/{second['id']}/status", json={"status": "bushed", "on_date": "2026-11-11"})
    with env.Session() as db:
        db.add(AutomationPreference(user_id=1, key="auto_stage", mode="manual"))
        db.commit()
        assert advance_ready_cycles(db, date(2026, 12, 20)) == 0


# Migration -----------------------------------------------------------------------

def test_migration_turns_single_harvests_into_entries_and_closes_empty_cycles(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'production.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    with Session() as db:
        db.add_all([
            Table(id=1, table_number=6),
            Batch(id=1, batch_number=1, start_date=date(2026, 1, 1)),
            Product(id=1, category="vegetable", name_encrypted=encrypt_text("ผัก").encode(), name_hash=hash_catalog_name("ผัก"), unit="kg"),
        ])
        db.flush()
        db.add(CropType(id=1, name="ผักกาด", nursery_days=10, growth_days=30, product_id=1))
        db.flush()
        db.add_all([
            CropCycle(id=1, table_id=1, batch_id=1, crop_type_id=1, nursery_start=date(2026, 9, 1),
                      status=CycleStatus.harvested, harvest_date=date(2026, 10, 15), harvest_quantity_kg=7.5),
            CropCycle(id=2, table_id=1, batch_id=1, crop_type_id=1, nursery_start=date(2026, 8, 1),
                      status=CycleStatus.harvested, transplant_date=date(2026, 8, 12)),
        ])
        db.add(StockMovement(id=1, product_id=1, quantity_delta=7.5, movement_type="receipt",
                             source_type="crop_cycle_harvest", source_id=1, occurred_at=datetime(2026, 10, 14, 17)))
        db.add(LotExpiryOverride(product_id=1, lot_key="harvest-1", expires_on=date(2026, 10, 25),
                                 reason_encrypted=encrypt_text("ห่อดี").encode()))
        db.add(StockWaste(product_id=1, lot_key="harvest-1", quantity=1, unit="kg", reason="expired"))
        db.commit()
    with engine.begin() as connection:
        connection.execute(text("UPDATE crop_cycles SET status = 'empty', expected_transplant_on = NULL, expected_ready_on = NULL WHERE id = 2"))
        connection.execute(text("UPDATE crop_cycles SET expected_transplant_on = NULL, expected_ready_on = NULL WHERE id = 1"))

    first = migrate_production_records(engine)
    second = migrate_production_records(engine)

    assert first == {"entries": 1, "movements": 1, "lot_keys": 2, "emptied": 1, "expected": 2}
    assert second == {"entries": 0, "movements": 0, "lot_keys": 0, "emptied": 0, "expected": 0}
    with Session() as db:
        entry = db.scalar(select(HarvestEntry))
        assert (entry.crop_cycle_id, entry.harvested_on, entry.quantity_kg) == (1, date(2026, 10, 15), 7.5)
        movement = db.get(StockMovement, 1)
        assert (movement.source_type, movement.source_id) == (HARVEST_ENTRY, entry.id)
        assert db.scalar(select(LotExpiryOverride.lot_key)) == f"harvest-entry-{entry.id}"
        assert db.scalar(select(StockWaste.lot_key)) == f"harvest-entry-{entry.id}"
        emptied = db.get(CropCycle, 2)
        assert emptied.status == CycleStatus.harvested
        assert (emptied.expected_transplant_on, emptied.expected_ready_on) == (date(2026, 8, 11), date(2026, 9, 11))
        cleanup = db.scalar(select(Activity).where(Activity.kind == "cleanup"))
        assert (cleanup.status, cleanup.title, cleanup.cycle_id) == ("done", "ทำความสะอาดโต๊ะ 6", 2)
        assert db.get(CropCycle, 1).expected_ready_on == date(2026, 10, 11)
    engine.dispose()


def test_activity_stock_source_is_used_for_seeds(env):
    new_cycle(env, seed_count=10)
    with env.Session() as db:
        assert db.scalar(select(StockMovement.source_type).where(StockMovement.product_id == 2, StockMovement.quantity_delta < 0)) == ACTIVITY
