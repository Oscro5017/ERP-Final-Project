"""Phase 3 step 4: grow tables hold several crops, counted in plants, free once cleaned."""
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import Batch, CropType, Product, Role, Table, User
from app.security import get_current_user
from app.services.activities import today_bangkok
from app.services.secure_fields import encrypt_text, hash_catalog_name


@pytest.fixture
def env():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False)
    with Session() as db:
        db.add_all([
            User(id=1, username="owner", password_hash="x", role=Role.owner),
            Table(id=1, table_number=1),
            Table(id=2, table_number=2),
            Batch(id=1, batch_number=1, start_date=date(2025, 1, 1)),
            Product(id=1, category="vegetable", name_encrypted=encrypt_text("คะน้า").encode(), name_hash=hash_catalog_name("คะน้า"), unit="kg"),
        ])
        db.flush()
        db.add_all([
            CropType(id=1, name="คะน้า", nursery_days=10, growth_days=30, product_id=1),
            CropType(id=2, name="ผักกาด", nursery_days=10, growth_days=25),
        ])
        db.commit()

    def override_db():
        with Session() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: User(id=1, username="owner", password_hash="x", role=Role.owner)
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


def cycle(client, table_id=1, crop_type_id=1, **extra):
    body = {"table_id": table_id, "batch_id": 1, "crop_type_id": crop_type_id, "nursery_start": "2025-01-01", **extra}
    response = client.post("/crop-cycles", json=body)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def board(client, table_id=1):
    return [row for row in client.get("/tables/board").json() if row["id"] == table_id][0]


def test_one_table_grows_several_crops_counted_in_plants(env):
    cycle(env, plant_count=120)
    cycle(env, crop_type_id=2, plant_count=50)
    row = board(env)
    assert (row["capacity_plants"], row["used_plants"], row["free_plants"], row["state"]) == (200, 170, 30, "partial")
    assert sorted((c["crop_name"], c["plants"]) for c in row["cycles"]) == [("คะน้า", 120), ("ผักกาด", 50)]
    assert all(c["days_since_sowing"] == (today_bangkok() - date(2025, 1, 1)).days for c in row["cycles"])
    cycle(env, crop_type_id=2, plant_count=30)
    assert board(env)["state"] == "full"
    assert board(env, 2)["state"] == "ready"


def test_unknown_counts_fill_the_table_and_seeds_stand_in_for_plants(env):
    cycle(env)
    assert board(env)["free_plants"] == 0
    cycle(env, table_id=2, seed_count=500)
    assert board(env, 2)["used_plants"] == 200
    assert env.patch("/tables/2", json={"capacity_plants": 600}).json()["capacity_plants"] == 600
    assert board(env, 2)["free_plants"] == 100
    assert env.patch("/tables/2", json={"capacity_plants": 0}).status_code == 422


def test_a_harvested_table_waits_for_cleaning_before_it_is_free(env):
    cycle_id = cycle(env, plant_count=150)
    env.post(f"/crop-cycles/{cycle_id}/harvests", json={"harvested_on": "2025-02-20", "quantity_kg": 9, "final": True})
    row = board(env)
    assert (row["state"], row["free_plants"]) == ("needs_cleaning", 50)
    assert row["cycles"][0]["awaiting_cleanup"] is True

    [cleanup] = env.get(f"/activities?cycle_id={cycle_id}&kind=cleanup").json()
    assert cleanup["status"] == "pending"
    env.post(f"/activities/{cleanup['id']}/status", json={"status": "done", "on_date": "2025-02-21"})
    row = board(env)
    assert (row["state"], row["free_plants"], row["cycles"]) == ("ready", 200, [])


def test_a_whole_table_cleaning_counts_only_after_the_harvest(env):
    cycle_id = cycle(env, plant_count=150, create_tasks=False)
    env.post(f"/crop-cycles/{cycle_id}/harvests", json={"harvested_on": "2025-02-20", "quantity_kg": 9, "final": True})
    env.post("/activities", json={"kind": "cleanup", "done_on": "2025-02-10", "table_ids": [1]})
    assert board(env)["state"] == "needs_cleaning"
    env.post("/activities", json={"kind": "cleanup", "done_on": "2025-02-22", "table_ids": [1]})
    assert board(env)["state"] == "ready"


def test_order_planting_counts_plants_and_fills_free_room(env):
    # History: 150 plants gave 15 kg, so 0.1 kg per plant.
    past = cycle(env, table_id=2, plant_count=150)
    env.post(f"/crop-cycles/{past}/harvests", json={"harvested_on": "2025-02-20", "quantity_kg": 15, "final": True})
    env.post("/activities", json={"kind": "cleanup", "done_on": "2025-02-21", "table_ids": [2]})
    cycle(env, table_id=1, crop_type_id=2, plant_count=80)  # table 1 keeps 120 free

    customer = env.post("/customers", json={"name": "ร้านสลัด"}).json()["id"]
    order = env.post("/sales-orders", json={"customer_id": customer, "lines": [
        {"product_id": 1, "quantity": 25, "delivery_date": "2030-01-01"},
    ], "auto_planting": False})
    assert order.status_code == 201, order.text
    line = order.json()["lines"][0]
    proposal = env.get(f"/sales-orders/lines/{line['id']}/planting").json()
    assert proposal["plants_needed"] == 250
    assert proposal["tables_needed"] == 2  # 120 on table 1, the rest on table 2
    assert {(t["id"], t["free_plants"]) for t in proposal["free_tables"]} == {(1, 120), (2, 200)}

    created = env.post(f"/sales-orders/lines/{line['id']}/planting", json={
        "table_ids": [1, 2], "nursery_start": str(today_bangkok()),
    })
    assert created.status_code in (200, 201), created.text
    counts = sorted(c["plant_count"] for c in env.get("/crop-cycles").json() if c["status"] == "nursery" and c["crop_type"]["id"] == 1)
    assert counts == [120, 130]
