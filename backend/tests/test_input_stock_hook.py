from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, inspect, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.migrations import migrate_input_product_mapping
from app.models import Batch, CropCycle, CropType, InputApplication, Product, Role, StockMovement, Table, User
from app.security import get_current_user
from app.services.products_stock import on_hand
from app.services.source_types import INPUT_APPLICATION


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
            CropCycle(id=1, table_id=1, batch_id=1, crop_type_id=1, nursery_start=date(2025, 1, 1), cycle_code="250101"),
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
    response = client.post("/products", json={"category": "fertilizer", "name": f"Input Product {unit}", "unit": unit})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def create_application(client, item_name="Fertilizer A", quantity=2, unit="kg", product_id=None, **extra):
    item = {"item_name": item_name, "quantity": quantity, "unit": unit, **extra}
    if product_id != "OMIT":
        item["product_id"] = product_id
    return client.post("/crop-cycles/1/input-applications", json={"category": "fertilizer", "items": [item]})


def test_input_mapping_migration_is_additive_and_idempotent():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE products (id INTEGER PRIMARY KEY)")
        connection.exec_driver_sql("CREATE TABLE input_items (id INTEGER PRIMARY KEY, name TEXT)")
        connection.exec_driver_sql("CREATE TABLE input_catalog (id INTEGER PRIMARY KEY, name TEXT)")
        connection.exec_driver_sql("INSERT INTO input_items VALUES (1, 'old item')")
        connection.exec_driver_sql("INSERT INTO input_catalog VALUES (1, 'old catalog')")
    migrate_input_product_mapping(engine)
    migrate_input_product_mapping(engine)
    assert {column["name"] for column in inspect(engine).get_columns("input_items")} == {"id", "name", "product_id"}
    assert {column["name"] for column in inspect(engine).get_columns("input_catalog")} == {"id", "name", "product_id"}


def test_mapped_application_deducts_stock_with_application_source_and_catalog_mapping():
    _, Session = make_db()
    with API(Session) as client:
        product_id = add_product(client)
        response = create_application(client, product_id=product_id)
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["items"][0]["product_id"] == product_id
        with Session() as db:
            movement = db.scalar(select(StockMovement).where(StockMovement.source_type == INPUT_APPLICATION))
            assert movement.source_id == body["id"]
            assert movement.movement_type == "application"
            assert movement.quantity_delta == -2
            assert on_hand(db, product_id) == -2


def test_edit_items_voids_old_deduction_and_records_new_quantity():
    _, Session = make_db()
    with API(Session) as client:
        product_id = add_product(client)
        app_id = create_application(client, quantity=2, product_id=product_id).json()["id"]
        response = client.patch(f"/input-applications/{app_id}", json={"items": [
            {"item_name": "Fertilizer A", "quantity": 3.5, "unit": "kg", "product_id": product_id},
        ]})
        assert response.status_code == 200, response.text
        with Session() as db:
            movements = db.scalars(select(StockMovement).where(StockMovement.source_type == INPUT_APPLICATION).order_by(StockMovement.id)).all()
            assert len(movements) == 2
            assert movements[0].voided_at is not None and movements[1].voided_at is None
            assert movements[1].quantity_delta == -3.5
            assert on_hand(db, product_id) == -3.5


def test_delete_application_voids_all_linked_movements():
    _, Session = make_db()
    with API(Session) as client:
        product_id = add_product(client)
        app_id = create_application(client, product_id=product_id).json()["id"]
        assert client.delete(f"/input-applications/{app_id}").status_code == 204
        with Session() as db:
            movement = db.scalar(select(StockMovement).where(StockMovement.source_type == INPUT_APPLICATION))
            assert movement.voided_at is not None
            assert on_hand(db, product_id) == 0


def test_metric_conversion_from_grams_to_kilograms():
    _, Session = make_db()
    with API(Session) as client:
        product_id = add_product(client, "kg")
        response = create_application(client, quantity=2000, unit="g", product_id=product_id)
        assert response.status_code == 201
        with Session() as db:
            assert on_hand(db, product_id) == -2


def test_unit_mismatch_keeps_application_and_returns_warning_without_movement():
    _, Session = make_db()
    with API(Session) as client:
        product_id = add_product(client, "kg")
        response = create_application(client, unit="l", product_id=product_id)
        assert response.status_code == 201, response.text
        assert response.json()["warnings"] == [f"unit_mismatch:{product_id}"]
        with Session() as db:
            assert db.scalar(select(InputApplication.id)) is not None
            assert db.scalar(select(StockMovement.id)) is None


def test_unmapped_application_preserves_old_behavior_without_stock_movement():
    _, Session = make_db()
    with API(Session) as client:
        response = create_application(client, product_id=None)
        assert response.status_code == 201
        assert response.json()["warnings"] == []
        with Session() as db:
            assert db.scalar(select(InputApplication.id)) is not None
            assert db.scalar(select(StockMovement.id)) is None


def test_catalog_remembers_product_mapping_when_next_application_omits_product_id():
    _, Session = make_db()
    with API(Session) as client:
        product_id = add_product(client)
        assert create_application(client, product_id=product_id).status_code == 201
        second = create_application(client, item_name="Fertilizer A", quantity=1, product_id="OMIT")
        assert second.status_code == 201, second.text
        assert second.json()["items"][0]["product_id"] == product_id
        with Session() as db:
            assert on_hand(db, product_id) == -3


def test_explicit_null_clears_catalog_product_mapping():
    _, Session = make_db()
    with API(Session) as client:
        product_id = add_product(client)
        assert create_application(client, product_id=product_id).status_code == 201
        assert create_application(client, item_name="Fertilizer A", product_id=None).status_code == 201
        response = create_application(client, item_name="Fertilizer A", product_id="OMIT")
        assert response.status_code == 201, response.text
        assert response.json()["items"][0]["product_id"] is None
        with Session() as db:
            assert on_hand(db, product_id) == -2


def test_invalid_product_is_rejected_without_creating_application():
    _, Session = make_db()
    with API(Session) as client:
        response = create_application(client, product_id=9999)
        assert response.status_code == 422
        with Session() as db:
            assert db.scalar(select(InputApplication.id)) is None


def test_hook_failure_rolls_back_application_and_movement(monkeypatch):
    _, Session = make_db()
    with API(Session) as client:
        product_id = add_product(client)

        def fail(*_args, **_kwargs):
            raise RuntimeError("injected input hook failure")

        import app.routers.input_applications as router_module

        monkeypatch.setattr(router_module, "sync_input_application_stock", fail)
        with pytest.raises(RuntimeError, match="injected input hook failure"):
            create_application(client, product_id=product_id)
        with Session() as db:
            assert db.scalar(select(InputApplication.id)) is None
            assert db.scalar(select(StockMovement.id)) is None


def test_input_endpoint_requires_authentication():
    _, Session = make_db()
    with API(Session) as client:
        app.dependency_overrides.pop(get_current_user, None)
        response = create_application(client)
        assert response.status_code == 401
