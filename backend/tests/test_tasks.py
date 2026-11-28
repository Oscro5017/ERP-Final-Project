from datetime import date, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import Batch, CropCycle, CropType, Role, Table, Activity, User
from app.security import hash_password


def build_test_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return engine, SessionLocal


def setup_test_data(SessionLocal):
    with SessionLocal() as db:
        user = User(username="test_owner", password_hash=hash_password("owner123"), role=Role.owner)
        developer = User(username="test_developer", password_hash=hash_password("developer123"), role=Role.developer)
        db.add_all([user, developer])
        table = Table(table_number=5)
        batch = Batch(batch_number=1, start_date=date(2026, 9, 1), week_offset=0)
        crop_type = CropType(name="Green Oak", nursery_days=14, growth_days=28)
        db.add_all([table, batch, crop_type])
        db.commit()


def test_task_auto_generation_on_crop_cycle_lifecycle():
    _, SessionLocal = build_test_db()
    setup_test_data(SessionLocal)

    def override_get_db():
        with SessionLocal() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    # Login
    login_resp = client.post("/auth/login", json={"username": "test_owner", "password": "owner123"})
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Create CropCycle in 'nursery' status
    nursery_date = date(2026, 9, 22)
    cycle_payload = {
        "table_id": 1,
        "batch_id": 1,
        "crop_type_id": 1,
        "nursery_start": nursery_date.isoformat(),
        "status": "nursery",
    }
    create_resp = client.post("/crop-cycles", json=cycle_payload, headers=headers)
    assert create_resp.status_code == 201
    cycle_id = create_resp.json()["id"]

    # Verify auto task "ย้ายปลูก โต๊ะ 5" is created
    tasks_resp = client.get("/tasks?status=pending", headers=headers)
    assert tasks_resp.status_code == 200
    tasks = tasks_resp.json()
    assert len(tasks) == 1
    t1 = tasks[0]
    assert "ย้ายปลูก" in t1["title"]
    assert "5" in t1["title"]
    expected_transplant_due = nursery_date + timedelta(days=14)
    assert t1["due_date"] == expected_transplant_due.isoformat()
    assert t1["source"] == "auto"
    assert t1["status"] == "pending"
    assert t1["cycle_id"] == cycle_id

    # 2. Update nursery_start while still nursery -> should update due_date without creating duplicate
    new_nursery_date = date(2026, 9, 23)
    patch_cycle_resp = client.patch(f"/crop-cycles/{cycle_id}", json={"nursery_start": new_nursery_date.isoformat()}, headers=headers)
    assert patch_cycle_resp.status_code == 200

    tasks_resp = client.get("/tasks?status=pending", headers=headers)
    tasks = tasks_resp.json()
    assert len(tasks) == 1
    assert tasks[0]["due_date"] == (new_nursery_date + timedelta(days=14)).isoformat()

    # 3. Mark the transplant task done manually
    task_id = tasks[0]["id"]
    mark_done_resp = client.patch(f"/tasks/{task_id}", json={"status": "done"}, headers=headers)
    assert mark_done_resp.status_code == 200
    assert mark_done_resp.json()["status"] == "done"

    # 4. Change CropCycle status to "bushed" (สร้างพุ่ม)
    transplant_date = date(2026, 10, 7)
    cycle_bushed_resp = client.patch(
        f"/crop-cycles/{cycle_id}",
        json={"status": "bushed", "transplant_date": transplant_date.isoformat()},
        headers=headers,
    )
    assert cycle_bushed_resp.status_code == 200

    # Verify:
    # - New task "เตรียมเก็บเกี่ยว โต๊ะ 5" is created with due_date = transplant_date + 28 days
    # - No duplicate of previous transplant task (which is already done)
    all_tasks_resp = client.get("/tasks", headers=headers)
    all_tasks = all_tasks_resp.json()
    assert len(all_tasks) == 2  # 1 done transplant task, 1 pending harvest prep task

    pending_tasks = client.get("/tasks?status=pending", headers=headers).json()
    assert len(pending_tasks) == 1
    t2 = pending_tasks[0]
    assert "เตรียมเก็บเกี่ยว" in t2["title"]
    assert "5" in t2["title"]
    expected_harvest_due = transplant_date + timedelta(days=28)
    assert t2["due_date"] == expected_harvest_due.isoformat()

    # 5. Change CropCycle status to "harvested" (เก็บเกี่ยว)
    cycle_harvest_resp = client.patch(
        f"/crop-cycles/{cycle_id}",
        json={"status": "harvested"},
        headers=headers,
    )
    assert cycle_harvest_resp.status_code == 200

    # Verify:
    # - New task "ทำความสะอาดโต๊ะ 5" is created with due_date = today + 1
    pending_tasks = client.get("/tasks?status=pending", headers=headers).json()
    assert len(pending_tasks) == 1
    t3 = pending_tasks[0]
    assert "ทำความสะอาดโต๊ะ" in t3["title"]
    assert t3["due_date"] == (date.today() + timedelta(days=1)).isoformat()

    app.dependency_overrides.clear()


def test_manual_tasks_crud_and_filters():
    _, SessionLocal = build_test_db()
    setup_test_data(SessionLocal)

    def override_get_db():
        with SessionLocal() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    login_resp = client.post("/auth/login", json={"username": "test_owner", "password": "owner123"})
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Create manual task
    due = date(2026, 9, 25)
    create_resp = client.post(
        "/tasks",
        json={
            "title": "สั่งซื้อฟองน้ำเพาะเมล็ด",
            "due_date": due.isoformat(),
            "status": "pending",
            "source": "manual",
        },
        headers=headers,
    )
    assert create_resp.status_code == 201
    task_data = create_resp.json()
    task_id = task_data["id"]
    assert task_data["title"] == "สั่งซื้อฟองน้ำเพาะเมล็ด"
    assert task_data["is_masked"] is False
    assert task_data["source"] == "manual"
    assert task_data["status"] == "pending"

    with SessionLocal() as db:
        stored_task = db.get(Activity, task_id)
        assert stored_task.is_encrypted is True
        assert stored_task.title != "สั่งซื้อฟองน้ำเพาะเมล็ด"
        assert stored_task.title.startswith("gAAAA")

    owner_search = client.get("/tasks?q=ฟองน้ำ", headers=headers)
    assert owner_search.status_code == 200
    assert [task["id"] for task in owner_search.json()] == [task_id]

    dev_login = client.post("/auth/login", json={"username": "test_developer", "password": "developer123"})
    dev_headers = {"Authorization": f"Bearer {dev_login.json()['access_token']}"}
    developer_tasks = client.get("/tasks", headers=dev_headers)
    assert developer_tasks.status_code == 200
    masked_task = developer_tasks.json()[0]
    assert masked_task["title"].startswith("gAAAA")
    assert masked_task["is_masked"] is True
    assert client.get("/tasks?q=ฟองน้ำ", headers=dev_headers).status_code == 403

    # 2. Filter tasks by status and date range
    resp = client.get("/tasks?status=pending&from=2026-09-20&to=2026-09-30", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 1

    resp_empty = client.get("/tasks?status=pending&from=2026-10-01", headers=headers)
    assert resp_empty.status_code == 200
    assert len(resp_empty.json()) == 0

    # 3. Mark task done
    patch_resp = client.patch(f"/tasks/{task_id}", json={"status": "done"}, headers=headers)
    assert patch_resp.status_code == 200
    assert patch_resp.json()["status"] == "done"

    # 4. Filter done tasks
    resp_done = client.get("/tasks?status=done", headers=headers)
    assert len(resp_done.json()) == 1

    # 5. Delete task
    del_resp = client.delete(f"/tasks/{task_id}", headers=headers)
    assert del_resp.status_code == 204

    resp_after_del = client.get("/tasks", headers=headers)
    assert len(resp_after_del.json()) == 0

    app.dependency_overrides.clear()
