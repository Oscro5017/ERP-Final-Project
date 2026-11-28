from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, inspect, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.migrations import migrate_crop_type_product_mapping
from app.models import HarvestEntry, Batch, CropCycle, CropType, Product, Role, StockMovement, Table, User
from app.security import get_current_user
from app.services.products_stock import on_hand
from app.services.source_types import HARVEST_ENTRY


def make_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def enable_fk(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with Session() as db:
        db.add_all([
            User(id=1, username="owner", password_hash="unused", role=Role.owner),
            Table(id=1, table_number=1),
            Batch(id=1, batch_number=1, start_date=date(2025, 1, 1)),
            CropType(id=1, name="Green Oak", nursery_days=14, growth_days=30),
        ])
        db.commit()
    return engine, Session


class API:
    def __init__(self, Session):
        self.Session = Session

    def __enter__(self):
        def override_db():
            with self.Session() as db:
                yield db

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_current_user] = lambda: User(
            id=1, username="owner", password_hash="unused", role=Role.owner
        )
        self.client = TestClient(app)
        return self.client

    def __exit__(self, *_):
        app.dependency_overrides.clear()


def add_product(client, unit="kg"):
    response = client.post("/products", json={"category": "vegetable", "name": "Green Oak", "unit": unit})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def create_cycle(client, quantity=None):
    response = client.post("/crop-cycles", json={
        "table_id": 1,
        "batch_id": 1,
        "crop_type_id": 1,
        "nursery_start": "2025-01-01",
        "harvest_quantity_kg": quantity,
    })
    assert response.status_code == 201, response.text
    return response


def map_product(client, product_id):
    return client.patch("/crop-types/1/product-mapping", json={"product_id": product_id})


def test_mapping_migration_is_additive_and_idempotent():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE crop_types (id INTEGER PRIMARY KEY, name VARCHAR(80) NOT NULL)")
        connection.exec_driver_sql("INSERT INTO crop_types (id, name) VALUES (1, 'Existing')")
        connection.exec_driver_sql("CREATE TABLE products (id INTEGER PRIMARY KEY)")
    migrate_crop_type_product_mapping(engine)
    migrate_crop_type_product_mapping(engine)
    inspector = inspect(engine)
    assert {col["name"] for col in inspector.get_columns("crop_types")} == {"id", "name", "product_id"}
    assert bool(inspector.get_indexes("crop_types")[0]["unique"])
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT name, product_id FROM crop_types WHERE id=1").one() == ("Existing", None)


def test_harvest_create_writes_one_positive_linked_movement_and_repeat_is_idempotent():
    _, Session = make_db()
    with API(Session) as client:
        product_id = add_product(client)
        assert map_product(client, product_id).status_code == 200
        response = create_cycle(client, 12.5)
        cycle_id = response.json()["id"]
        with Session() as db:
            movements = db.scalars(select(StockMovement).where(StockMovement.source_type == HARVEST_ENTRY)).all()
            assert len(movements) == 1
            # One receipt per harvest entry; the entry belongs to the cycle.
            assert db.get(HarvestEntry, movements[0].source_id).crop_cycle_id == cycle_id
            assert movements[0].movement_type == "receipt"
            assert movements[0].quantity_delta == 12.5
            assert on_hand(db, product_id) == 12.5
        assert client.patch(f"/crop-cycles/{cycle_id}", json={"harvest_quantity_kg": 12.5}).status_code == 200
        with Session() as db:
            assert len(db.scalars(select(StockMovement).where(StockMovement.source_type == HARVEST_ENTRY, StockMovement.voided_at.is_(None))).all()) == 1
            assert on_hand(db, product_id) == 12.5


@pytest.mark.parametrize("unit", ["กก.", "กิโลกรัม"])
def test_thai_kg_aliases_are_supported_for_harvest_mapping(unit):
    _, Session = make_db()
    with API(Session) as client:
        product_id = add_product(client, unit=unit)
        assert map_product(client, product_id).status_code == 200
        response = create_cycle(client, 2.25)
        assert response.json()["warnings"] == []
        with Session() as db:
            assert on_hand(db, product_id) == 2.25


def test_edit_quantity_voids_old_and_records_new_movement():
    _, Session = make_db()
    with API(Session) as client:
        product_id = add_product(client)
        map_product(client, product_id)
        cycle_id = create_cycle(client, 5).json()["id"]
        assert client.patch(f"/crop-cycles/{cycle_id}", json={"harvest_quantity_kg": 8.25}).status_code == 200
        with Session() as db:
            entries = db.scalars(select(StockMovement).where(StockMovement.source_type == HARVEST_ENTRY).order_by(StockMovement.id)).all()
            assert len(entries) == 2 and entries[0].voided_at is not None and entries[1].voided_at is None
            assert on_hand(db, product_id) == 8.25


@pytest.mark.parametrize("quantity", [0, None])
def test_clearing_harvest_quantity_voids_existing_movement(quantity):
    _, Session = make_db()
    with API(Session) as client:
        product_id = add_product(client)
        map_product(client, product_id)
        cycle_id = create_cycle(client, 4).json()["id"]
        response = client.patch(f"/crop-cycles/{cycle_id}", json={"harvest_quantity_kg": quantity})
        assert response.status_code == 200
        with Session() as db:
            movement = db.scalar(select(StockMovement).where(StockMovement.source_type == HARVEST_ENTRY))
            assert movement.voided_at is not None
            assert on_hand(db, product_id) == 0


def test_unmapped_harvest_saves_with_warning_and_no_movement():
    _, Session = make_db()
    with API(Session) as client:
        response = create_cycle(client, 3.5)
        assert response.json()["warnings"] == ["no_product_mapping"]
        with Session() as db:
            assert db.scalar(select(StockMovement.id)) is None


def test_non_kg_product_saves_mapping_but_harvest_warns_without_movement():
    _, Session = make_db()
    with API(Session) as client:
        product_id = add_product(client, unit="l")
        assert map_product(client, product_id).status_code == 200
        response = create_cycle(client, 3)
        assert response.json()["warnings"] == [f"unit_mismatch:{product_id}"]
        with Session() as db:
            assert db.scalar(select(StockMovement.id)) is None


def test_mapping_change_reconciles_existing_harvest_and_soft_delete_voids_it():
    _, Session = make_db()
    with API(Session) as client:
        first_product = add_product(client)
        assert map_product(client, first_product).status_code == 200
        cycle_id = create_cycle(client, 6).json()["id"]
        response = client.post("/products", json={"category": "vegetable", "name": "Green Oak 2", "unit": "kg"})
        second_product = response.json()["id"]
        assert map_product(client, second_product).status_code == 200
        with Session() as db:
            assert on_hand(db, first_product) == 0
            assert on_hand(db, second_product) == 6
        assert client.delete(f"/crop-cycles/{cycle_id}").status_code == 204
        with Session() as db:
            assert on_hand(db, second_product) == 0


def test_duplicate_product_mapping_is_rejected():
    _, Session = make_db()
    with API(Session) as client:
        product_id = add_product(client)
        assert map_product(client, product_id).status_code == 200
        with Session() as db:
            db.add(CropType(id=2, name="Red Oak", nursery_days=12, growth_days=24))
            db.commit()
        response = client.patch("/crop-types/2/product-mapping", json={"product_id": product_id})
        assert response.status_code == 409


def test_mapping_endpoint_rejects_missing_product_and_accepts_clear():
    _, Session = make_db()
    with API(Session) as client:
        assert client.patch("/crop-types/1/product-mapping", json={"product_id": 999}).status_code == 422
        assert client.patch("/crop-types/1/product-mapping", json={"product_id": None}).status_code == 200


def test_mapping_endpoint_rejects_inactive_product():
    _, Session = make_db()
    with API(Session) as client:
        product_id = add_product(client)
        assert client.patch(f"/products/{product_id}", json={"is_active": False}).status_code == 200
        assert client.patch("/crop-types/1/product-mapping", json={"product_id": product_id}).status_code == 422


def test_hook_failure_rolls_back_crop_cycle_and_stock_movement(monkeypatch):
    _, Session = make_db()
    with API(Session) as client:
        product_id = add_product(client)
        assert map_product(client, product_id).status_code == 200

        def fail(*_args, **_kwargs):
            raise RuntimeError("injected harvest hook failure")

        import app.routers.crop_cycles as crop_cycles_router

        monkeypatch.setattr(crop_cycles_router, "sync_crop_cycle_harvest_stock", fail)
        with pytest.raises(RuntimeError, match="injected harvest hook failure"):
            create_cycle(client, 9)
        with Session() as db:
            assert db.scalar(select(CropCycle.id)) is None
            assert db.scalar(select(StockMovement.id)) is None


def test_mapping_endpoint_requires_authentication():
    _, Session = make_db()
    with API(Session) as client:
        app.dependency_overrides.pop(get_current_user, None)
        response = client.patch("/crop-types/1/product-mapping", json={"product_id": None})
        assert response.status_code == 401
