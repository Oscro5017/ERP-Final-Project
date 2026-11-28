from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import Batch, CropCycle, CropType, Role, Table, User
from app.security import hash_password
from app.services.input_catalog import upsert_input_catalog
from app.services.secure_fields import decrypt_text, hash_catalog_name, normalize_catalog_name


def build_test_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return engine, SessionLocal


def test_upsert_input_catalog_creates_and_updates_item():
    _, SessionLocal = build_test_db()

    with SessionLocal() as db:
        db.add(User(username="phase1_owner_1", password_hash=hash_password("owner123"), role=Role.owner))
        db.commit()

        item = upsert_input_catalog(db, "ปุ๋ย A", "ลิตร", "ปุ๋ย")
        assert decrypt_text(item.name_encrypted) == "ปุ๋ย A"
        assert item.use_count == 1

        updated = upsert_input_catalog(db, "ปุ๋ย a", "ถุง", "ยา")
        assert updated.id == item.id
        assert updated.name_hash == hash_catalog_name(" ปุ๋ย A ")
        assert updated.use_count == 2
        assert updated.last_unit == "ถุง"
        assert updated.last_category == "ยา"


def test_catalog_name_normalization_and_hash_are_stable():
    normalized = normalize_catalog_name("  CAFÉ  ")
    assert normalized == normalize_catalog_name("cafe\u0301")
    assert hash_catalog_name("  CAFÉ  ") == hash_catalog_name("cafe\u0301")
    assert hash_catalog_name("cafe") != hash_catalog_name("café")


def test_get_input_catalog_suggestions_returns_matches():
    _, SessionLocal = build_test_db()

    with SessionLocal() as db:
        db.add(User(username="phase1_owner_2", password_hash=hash_password("owner123"), role=Role.owner))
        db.add_all([
            Table(table_number=1),
            Batch(batch_number=1, start_date=date(2025, 1, 1), week_offset=0),
            CropType(name="Green Oak Test", nursery_days=10, growth_days=20),
        ])
        db.commit()

        cycle = CropCycle(table_id=1, batch_id=1, crop_type_id=1, nursery_start=date(2025, 1, 1), status="nursery")
        db.add(cycle)
        db.commit()

        upsert_input_catalog(db, "ปุ๋ย A", "ลิตร", "ปุ๋ย")
        upsert_input_catalog(db, "ปุ๋ย a", "ถุง", "ปุ๋ย")
        upsert_input_catalog(db, "ยาฆ่าแมลง A", "ขวด", "ยา")
        db.commit()

    def override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    login_response = client.post("/auth/login", json={"username": "phase1_owner_2", "password": "owner123"})
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]

    response = client.get("/input-catalog/suggestions?q=ปุ๋ย&limit=1", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["items"]) == 1
    assert payload["items"][0]["item_name"] == "ปุ๋ย A"
    assert payload["items"][0]["use_count"] == 2
    app.dependency_overrides.clear()
