from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import Batch, CropCycle, CropType, InputApplication, InputItem, Role, Table, User
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


def test_input_applications_crud_and_developer_access():
    _, SessionLocal = build_test_db()

    with SessionLocal() as db:
        db.add_all([
            User(username="owner_crud", password_hash=hash_password("owner123"), role=Role.owner),
            User(username="dev_crud", password_hash=hash_password("developer123"), role=Role.developer),
            Table(table_number=2),
            Batch(batch_number=2, start_date=date(2025, 1, 1), week_offset=0),
            CropType(name="Red Oak Test", nursery_days=14, growth_days=28),
        ])
        db.commit()

        cycle = CropCycle(table_id=1, batch_id=1, crop_type_id=1, nursery_start=date(2025, 1, 1), status="nursery")
        db.add(cycle)
        db.commit()
        cycle_id = cycle.id

    def override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    # 1. Login as owner to create an application
    login_resp = client.post("/auth/login", json={"username": "owner_crud", "password": "owner123"})
    assert login_resp.status_code == 200
    owner_token = login_resp.json()["access_token"]
    headers_owner = {"Authorization": f"Bearer {owner_token}"}

    validation_marker = "PRIVATE-INPUT-MARKER"
    invalid_resp = client.post(
        f"/crop-cycles/{cycle_id}/input-applications",
        json={
            "note": validation_marker,
            "items": [{"item_name": validation_marker, "quantity": 0, "unit": "ml"}],
        },
        headers=headers_owner,
    )
    assert invalid_resp.status_code == 422
    assert validation_marker not in invalid_resp.text

    create_payload = {
        "applied_date": "2025-06-01",
        "category": "ปุ๋ย",
        "note": "รดหลังฝนตก",
        "items": [
            {"item_name": "ปุ๋ยสูตร 1", "quantity": 2.5, "unit": "ลิตร"},
            {"item_name": "แคลเซียมโบรอน", "quantity": 1.0, "unit": "ขวด"},
        ],
    }
    create_resp = client.post(f"/crop-cycles/{cycle_id}/input-applications", json=create_payload, headers=headers_owner)
    assert create_resp.status_code == 201
    created_data = create_resp.json()
    assert created_data["category"] == "ปุ๋ย"
    assert created_data["is_masked"] is False
    assert len(created_data["items"]) == 2
    app_id = created_data["id"]

    # 2. Login as developer and verify access to read and update
    dev_login = client.post("/auth/login", json={"username": "dev_crud", "password": "developer123"})
    assert dev_login.status_code == 200
    dev_token = dev_login.json()["access_token"]
    headers_dev = {"Authorization": f"Bearer {dev_token}"}

    list_resp = client.get(f"/crop-cycles/{cycle_id}/input-applications", headers=headers_dev)
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1
    masked_data = list_resp.json()[0]
    assert masked_data["is_masked"] is True
    assert masked_data["note"].startswith("gAAAA")
    assert masked_data["items"][0]["item_name"].startswith("gAAAA")
    assert masked_data["items"][0]["quantity"].startswith("gAAAA")
    assert masked_data["items"][0]["is_masked"] is True
    suggestions_resp = client.get("/input-catalog/suggestions?q=ปุ๋ย", headers=headers_dev)
    assert suggestions_resp.json() == {"items": [], "is_masked": True}

    with SessionLocal() as db:
        stored_item = db.query(InputItem).first()
        stored_app = db.query(InputApplication).first()
        assert "ปุ๋ยสูตร 1".encode("utf-8") not in stored_item.item_name_encrypted
        assert "รดหลังฝนตก".encode("utf-8") not in stored_app.note_encrypted

    # 3. Update application (PATCH)
    update_payload = {
        "applied_date": "2025-06-02",
        "category": "ยา",
        "note": "ปรับลดปริมาณ",
        "items": [
            {"item_name": "ยาชีวภาพ", "quantity": 1.5, "unit": "ลิตร"}
        ],
    }
    patch_resp = client.patch(f"/input-applications/{app_id}", json=update_payload, headers=headers_dev)
    assert patch_resp.status_code == 200
    patched_data = patch_resp.json()
    assert patched_data["category"] == "ยา"
    assert patched_data["applied_date"] == "2025-06-02"
    assert len(patched_data["items"]) == 1
    assert patched_data["is_masked"] is True
    assert patched_data["items"][0]["item_name"].startswith("gAAAA")
    owner_read = client.get(f"/crop-cycles/{cycle_id}/input-applications", headers=headers_owner).json()[0]
    assert owner_read["items"][0]["item_name"] == "ยาชีวภาพ"

    # 4. Delete application (DELETE)
    del_resp = client.delete(f"/input-applications/{app_id}", headers=headers_owner)
    assert del_resp.status_code == 204

    # Verify deleted
    list_after_del = client.get(f"/crop-cycles/{cycle_id}/input-applications", headers=headers_owner)
    assert list_after_del.status_code == 200
    assert len(list_after_del.json()) == 0

    app.dependency_overrides.clear()
