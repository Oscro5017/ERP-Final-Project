from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.migrations import migrate_phase1c
from app.models import (
    Batch,
    CropCycle,
    CropType,
    Customer,
    Role,
    Table,
    Activity,
    User,
)
from app.security import hash_password


def build_test_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return engine, session_local


def override_database(session_local):
    def override_get_db():
        with session_local() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db


def get_owner_headers(client):
    response = client.post("/auth/login", json={"username": "phase1c_owner", "password": "owner123"})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_crop_cycle_status_history_and_harvest_quantity():
    _, session_local = build_test_db()
    with session_local() as db:
        db.add(User(username="phase1c_owner", password_hash=hash_password("owner123"), role=Role.owner))
        db.add_all([
            Table(table_number=1),
            Batch(batch_number=1, start_date=date(2026, 10, 20), week_offset=0),
            CropType(name="Phase 1c Oak", nursery_days=14, growth_days=28),
        ])
        db.commit()

    override_database(session_local)
    client = TestClient(app)
    try:
        headers = get_owner_headers(client)
        created = client.post("/crop-cycles", headers=headers, json={
            "table_id": 1,
            "batch_id": 1,
            "crop_type_id": 1,
            "nursery_start": "2026-10-20",
            "status": "nursery",
        })
        assert created.status_code == 201
        cycle_id = created.json()["id"]

        history = client.get(f"/crop-cycles/{cycle_id}/status-log", headers=headers)
        assert history.status_code == 200
        assert len(history.json()) == 1
        assert history.json()[0]["from_status"] is None
        assert history.json()[0]["to_status"] == "nursery"
        assert history.json()[0]["changed_at"]

        updated = client.patch(f"/crop-cycles/{cycle_id}", headers=headers, json={
            "status": "harvested",
            "harvest_quantity_kg": 4.25,
        })
        assert updated.status_code == 200
        assert updated.json()["harvest_quantity_kg"] == 4.25

        history = client.get(f"/crop-cycles/{cycle_id}/status-log", headers=headers)
        assert len(history.json()) == 2
        assert history.json()[1]["from_status"] == "nursery"
        assert history.json()[1]["to_status"] == "harvested"
    finally:
        app.dependency_overrides.clear()


def test_soft_deletes_keep_rows_and_hide_them_from_lists():
    _, session_local = build_test_db()
    with session_local() as db:
        db.add_all([
            User(username="phase1c_owner", password_hash=hash_password("owner123"), role=Role.owner),
            User(username="phase1c_developer", password_hash=hash_password("developer123"), role=Role.developer),
            Table(table_number=1),
            Batch(batch_number=1, start_date=date(2026, 10, 20), week_offset=0),
            CropType(name="Phase 1c Lettuce", nursery_days=14, growth_days=28),
        ])
        db.commit()

    override_database(session_local)
    client = TestClient(app)
    try:
        owner_headers = get_owner_headers(client)
        cycle_response = client.post("/crop-cycles", headers=owner_headers, json={
            "table_id": 1,
            "batch_id": 1,
            "crop_type_id": 1,
            "nursery_start": "2026-10-20",
            "status": "nursery",
        })
        cycle_id = cycle_response.json()["id"]

        customer_response = client.post("/customers", headers=owner_headers, json={"name": "Private Name", "contact": "Private Contact"})
        customer_id = customer_response.json()["id"]
        developer_login = client.post("/auth/login", json={"username": "phase1c_developer", "password": "developer123"})
        developer_headers = {"Authorization": f"Bearer {developer_login.json()['access_token']}"}
        masked_customer = client.get("/customers", headers=developer_headers).json()[0]
        assert masked_customer["name"].startswith("gAAAA")
        assert masked_customer["contact"].startswith("gAAAA")
        assert masked_customer["is_masked"] is True

        application_response = client.post("/activities", headers=owner_headers, json={
            "kind": "fertilize",
            "done_on": "2026-10-20",
            "cycle_ids": [cycle_id],
            "items": [{"item_name": "Phase 1c test mix", "quantity": 1, "unit": "ลิตร"}],
        })
        application_id = application_response.json()["id"]

        task_response = client.post("/tasks", headers=owner_headers, json={
            "title": "Phase 1c test task",
            "due_date": "2026-10-21",
            "status": "pending",
            "source": "manual",
        })
        task_id = task_response.json()["id"]

        assert client.delete(f"/activities/{application_id}", headers=owner_headers).status_code == 204
        assert client.get(f"/activities?cycle_id={cycle_id}&kind=fertilize", headers=owner_headers).json() == []
        assert client.delete(f"/customers/{customer_id}", headers=owner_headers).status_code == 204
        assert client.get("/customers", headers=owner_headers).json() == []
        assert client.get("/customers", headers=developer_headers).json() == []
        assert client.delete(f"/tasks/{task_id}", headers=owner_headers).status_code == 204
        assert all(task["id"] != task_id for task in client.get("/tasks", headers=owner_headers).json())
        assert client.delete(f"/crop-cycles/{cycle_id}", headers=owner_headers).status_code == 204
        assert client.get("/tasks", headers=owner_headers).json() == []
        assert client.get("/crop-cycles", headers=owner_headers).json() == []

        with session_local() as db:
            assert db.get(CropCycle, cycle_id).deleted_at is not None
            assert db.get(Customer, customer_id).deleted_at is not None
            assert db.get(Activity, application_id).deleted_at is not None
            assert db.get(Activity, task_id).deleted_at is not None
    finally:
        app.dependency_overrides.clear()


def test_phase1c_migration_backfills_existing_cycles_idempotently():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE crop_cycles (id INTEGER PRIMARY KEY, status VARCHAR(32) NOT NULL, nursery_start DATE NOT NULL)")
        connection.exec_driver_sql("INSERT INTO crop_cycles (id, status, nursery_start) VALUES (1, 'nursery', '2026-10-20')")

    migrate_phase1c(engine)
    migrate_phase1c(engine)

    with engine.connect() as connection:
        row = connection.exec_driver_sql("SELECT id, status, created_at, updated_at, deleted_at FROM crop_cycles WHERE id = 1").mappings().one()
        assert row["id"] == 1
        assert row["status"] == "nursery"
        assert row["created_at"] is not None
        assert row["updated_at"] is not None
        assert row["deleted_at"] is None
        logs = connection.exec_driver_sql("SELECT cycle_id, from_status, to_status, changed_at FROM crop_cycle_status_logs").mappings().all()
        assert len(logs) == 1
        assert logs[0]["cycle_id"] == 1
        assert logs[0]["from_status"] is None
        assert logs[0]["to_status"] == "nursery"
        assert logs[0]["changed_at"] == row["created_at"]
