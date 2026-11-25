from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import Product, Role, StockMovement, User
from app.migrations import migrate_products_stock
from app.routers.products import create_product, delete_product, list_product_movements, list_products, update_product, adjust_product
from app.schemas import ProductAdjustmentCreate, ProductCreate, ProductUpdate
from app.security import get_current_user
from app.services.products_stock import convert_quantity, on_hand, record_movement, void_source_movements
from app.services.secure_fields import encrypt_text


def make_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    @event.listens_for(engine, "connect")
    def enable_fk(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine)
    return engine, sessionmaker(bind=engine, autoflush=False, autocommit=False)


def test_migration_idempotency_and_foreign_key():
    engine = create_engine("sqlite:///:memory:")
    @event.listens_for(engine, "connect")
    def enable_fk(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")
    migrate_products_stock(engine)
    migrate_products_stock(engine)
    with engine.begin() as conn:
        with pytest.raises(Exception):
            conn.execute(text("INSERT INTO stock_movements (product_id, quantity_delta, movement_type, occurred_at, created_at, updated_at) VALUES (999, 1, 'receipt', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"))


def test_service_unit_conversion_grouping_void_and_rollback():
    engine, SessionLocal = make_db()
    with SessionLocal() as db:
        product = Product(category="fertilizer", name_encrypted=b"x", name_hash="hash-a", unit="kg")
        db.add(product)
        db.flush()
        record_movement(db, product.id, 500, "กรัม", "receipt", "purchase", 3)
        record_movement(db, product.id, -0.1, "kg", "shipment")
        assert on_hand(db, product.id) == 0.4
        assert void_source_movements(db, "purchase", 3) == 1
        assert on_hand(db, product.id) == -0.1
        assert void_source_movements(db, "purchase", 3) == 0
        assert on_hand(db, product.id) == -0.1
        receipt = next(m for m in list_product_movements(
            product.id, limit=50, offset=0, db=db, user=User(role=Role.owner)
        ) if m.source_type == "purchase")
        assert receipt.voided is True
        record_movement(db, product.id, 2, "kg", "adjustment")
        db.rollback()
    with SessionLocal() as db:
        assert db.query(StockMovement).count() == 0
    assert convert_quantity(2, "L", "ml") == 2000
    assert convert_quantity(1, "มิลลิลิตร", "ลิตร") == 0.001
    with pytest.raises(ValueError):
        convert_quantity(1, "kg", "l")


def test_movement_sign_validation_and_float_sum_tolerance():
    _, SessionLocal = make_db()
    with SessionLocal() as db:
        product = Product(category="other", name_encrypted=b"x", name_hash="hash-sign", unit="kg")
        db.add(product)
        db.flush()
        for bad_args in [
            (1, "kg", "unknown"),
            (-1, "kg", "receipt"),
            (1, "kg", "shipment"),
            (1, "kg", "application"),
            (0, "kg", "receipt"),
            (0, "kg", "adjustment"),
            (float("nan"), "kg", "receipt"),
        ]:
            with pytest.raises(ValueError):
                record_movement(db, product.id, *bad_args)
        for _ in range(10):
            record_movement(db, product.id, 0.1, "kg", "receipt")
        record_movement(db, product.id, -1, "kg", "shipment")
        assert on_hand(db, product.id) == 0
        assert db.query(StockMovement).filter_by(product_id=product.id).count() == 11


def test_product_api_crud_mask_duplicates_adjust_and_soft_delete():
    _, SessionLocal = make_db()
    with SessionLocal() as db:
        owner = User(id=1, username="owner", password_hash="unused", role=Role.owner)
        developer = User(id=2, username="developer", password_hash="unused", role=Role.developer)
        created = create_product(ProductCreate(category="vegetable", name="Sample Romaine", unit="kg", reorder_point=0.5), db, owner)
        assert created.name == "Sample Romaine"
        assert created.is_low is True
        product_id = created.id
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as duplicate_error:
            create_product(ProductCreate(category="vegetable", name=" sample romaine ", unit="kg"), db, owner)
        assert duplicate_error.value.status_code == 409 and "Sample Romaine" not in duplicate_error.value.detail
        masked = list_products(q=None, limit=50, offset=0, db=db, user=developer)
        assert masked.items[0].is_masked is True and masked.items[0].name.startswith("gAAAA")
        adjusted = adjust_product(product_id, ProductAdjustmentCreate(counted_quantity=800, unit="กรัม", note="private note"), db, owner)
        assert adjusted.on_hand == 0.8 and adjusted.is_low is False
        zero = adjust_product(product_id, ProductAdjustmentCreate(counted_quantity=0.8, unit="kg"), db, owner)
        assert zero.on_hand == 0.8
        assert db.query(StockMovement).filter_by(product_id=product_id).count() == 1
        movement_dev = list_product_movements(product_id, limit=50, offset=0, db=db, user=developer)[0]
        assert movement_dev.note.startswith("gAAAA") and movement_dev.is_masked
        movement_owner = list_product_movements(product_id, limit=50, offset=0, db=db, user=owner)[0]
        assert movement_owner.note == "private note"
        with pytest.raises(HTTPException) as unit_error:
            update_product(product_id, ProductUpdate(unit="l"), db, owner)
        assert unit_error.value.status_code == 409
        with pytest.raises(HTTPException) as bad_adjustment:
            adjust_product(product_id, ProductAdjustmentCreate(counted_quantity=2, unit="l"), db, owner)
        assert bad_adjustment.value.status_code == 422
        delete_product(product_id, db, owner)
        assert list_products(q=None, limit=50, offset=0, db=db, user=owner).total == 0
        assert db.query(StockMovement).filter_by(product_id=product_id).count() == 1


def test_product_search_skips_broken_token_and_negative_balance(caplog):
    _, SessionLocal = make_db()
    with SessionLocal() as db:
        product = Product(category="other", name_encrypted=b"bad-token", name_hash="bad-hash", unit="each")
        db.add(product)
        db.flush()
        db.add(StockMovement(product_id=product.id, quantity_delta=-2, movement_type="adjustment", occurred_at=datetime.now(UTC)))
        db.commit()
        product_id = product.id
    with SessionLocal() as db:
        owner = User(id=1, username="owner", password_hash="unused", role=Role.owner)
        result = list_products(q="anything", limit=50, offset=0, db=db, user=owner)
        assert result.total == 0
        unfiltered = list_products(q=None, limit=50, offset=0, db=db, user=owner).items[0]
        assert unfiltered.decrypt_failed is True and unfiltered.is_negative is True
        assert unfiltered.on_hand == -2
        assert "bad-token" not in caplog.text
        assert "bad-token" not in unfiltered.model_dump_json()


def test_product_list_query_is_grouped_and_owner_search_works():
    engine, SessionLocal = make_db()
    with SessionLocal() as db:
        db.add_all([
            Product(category="vegetable", name_encrypted=encrypt_text("Green Oak").encode("ascii"), name_hash="hash-1", unit="kg"),
            Product(category="seed", name_encrypted=encrypt_text("Oak Seed").encode("ascii"), name_hash="hash-2", unit="g"),
            Product(category="other", name_encrypted=encrypt_text("Hidden Item").encode("ascii"), name_hash="hash-3", unit="each", is_active=False),
        ])
        db.commit()
        owner = User(id=1, username="owner", password_hash="unused", role=Role.owner)
        query_count = 0
        def count_queries(_conn, _cursor, _statement, _params, _context, _many):
            nonlocal query_count
            query_count += 1
        event.listen(engine, "before_cursor_execute", count_queries)
        result = list_products(q="oak", category=None, include_inactive=False, limit=1, offset=0, db=db, user=owner)
        event.remove(engine, "before_cursor_execute", count_queries)
        assert result.total == 2 and len(result.items) == 1
        assert query_count == 2
        inactive = list_products(q=None, include_inactive=True, limit=10, offset=0, db=db, user=owner)
        assert inactive.total == 3
        second_page = list_products(q=None, include_inactive=True, limit=1, offset=1, db=db, user=owner)
        assert second_page.total == 3 and len(second_page.items) == 1


def test_products_http_routes_expose_owner_and_developer_contract():
    _, SessionLocal = make_db()

    def override_db():
        with SessionLocal() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: User(
        id=1, username="owner", password_hash="unused", role=Role.owner
    )
    try:
        client = TestClient(app)
        created = client.post("/products", json={
            "category": "vegetable", "name": "HTTP Test Product", "unit": "kg", "reorder_point": 0.5,
        })
        assert created.status_code == 201
        product_id = created.json()["id"]
        assert client.get("/products").json()["items"][0]["name"] == "HTTP Test Product"
        app.dependency_overrides[get_current_user] = lambda: User(
            id=2, username="developer", password_hash="unused", role=Role.developer
        )
        assert client.get("/products").json()["items"][0]["is_masked"] is True
        app.dependency_overrides[get_current_user] = lambda: User(
            id=1, username="owner", password_hash="unused", role=Role.owner
        )
        invalid_unit = client.post(f"/products/{product_id}/adjustments", json={
            "counted_quantity": 1, "unit": "l",
        })
        assert invalid_unit.status_code == 422
    finally:
        app.dependency_overrides.clear()
