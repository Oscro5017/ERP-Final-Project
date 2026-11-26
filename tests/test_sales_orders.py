from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import Batch, CropCycle, CropType, Role, SalesOrderCycle, Table, Task, User
from app.security import get_current_user
from app.services.sales_orders import today_bangkok


class Env:
    def __init__(self):
        self.engine = create_engine(
            "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        event.listen(self.engine, "connect", lambda conn, _: conn.execute("PRAGMA foreign_keys=ON"))
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=False)
        self.role = Role.owner
        with self.Session() as db:
            db.add_all([
                User(id=1, username="owner", password_hash="unused", role=Role.owner),
                *[Table(id=n, table_number=n) for n in (1, 2, 3)],
                Batch(id=1, batch_number=1, start_date=date(2025, 1, 1)),
                CropType(id=1, name="Green Oak", nursery_days=14, growth_days=28),
            ])
            db.commit()

        def override_db():
            with self.Session() as db:
                yield db

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_current_user] = lambda: User(
            id=1, username="user", password_hash="unused", role=self.role
        )
        self.client = TestClient(app)
        self.product = self.post("/products", {"category": "vegetable", "name": "กรีนโอ๊ค", "unit": "kg"})["id"]
        self.customer = self.post("/customers", {"name": "ลูกค้าลับ"})["id"]
        self.map_crop()

    def post(self, path, body, status=201):
        response = self.client.post(path, json=body)
        assert response.status_code == status, response.text
        return response.json()

    def patch(self, path, body, status=200):
        response = self.client.patch(path, json=body)
        assert response.status_code == status, response.text
        return response.json()

    def get(self, path):
        response = self.client.get(path)
        assert response.status_code == 200, response.text
        return response.json()

    def map_crop(self, product="default"):
        self.patch("/crop-types/1/product-mapping", {"product_id": self.product if product == "default" else product})

    def order(self, days=60, status=201, **extra):
        body = {
            "customer_id": self.customer,
            "lines": [{"product_id": self.product, "quantity": 25,
                       "delivery_date": str(today_bangkok() + timedelta(days=days))}],
        }
        body.update(extra)
        return self.post("/sales-orders", body, status)

    def done(self, order, index=0):
        return self.patch(f"/tasks/{order['lines'][index]['planting_task_id']}", {"status": "done"})


@pytest.fixture
def env():
    environment = Env()
    yield environment
    app.dependency_overrides.clear()


def test_order_computes_latest_sow_date_and_creates_task(env):
    order = env.order(days=60)
    line = order["lines"][0]
    expected = str(today_bangkok() + timedelta(days=60 - 42))
    assert line["latest_sow_date"] == expected
    assert line["planting_status"] == "waiting"
    task = env.get("/tasks")[0]
    assert (task["id"], task["due_date"], task["source"], task["order_line_id"]) == (
        line["planting_task_id"], expected, "auto", line["id"])
    assert order["order_no"] in task["title"] and task["planting_ready"] is False


def test_safety_days_move_sowing_earlier_and_late_is_flagged(env):
    order = env.order(days=43, safety_days=2)
    assert order["lines"][0]["latest_sow_date"] == str(today_bangkok() - timedelta(days=1))
    assert order["lines"][0]["planting_status"] == "late"
    assert env.order(days=42)["lines"][0]["planting_status"] == "waiting"


def test_each_line_has_its_own_delivery_and_task(env):
    today = today_bangkok()
    order = env.order(lines=[
        {"product_id": env.product, "quantity": 5, "delivery_date": str(today + timedelta(days=days))}
        for days in (50, 60)
    ])
    assert [line["latest_sow_date"] for line in order["lines"]] == [
        str(today + timedelta(days=8)), str(today + timedelta(days=18))]
    assert len({line["planting_task_id"] for line in order["lines"]}) == 2


def test_completing_task_only_prompts_then_creates_cycles(env):
    order = env.order()
    line = order["lines"][0]
    url = f"/sales-orders/lines/{line['id']}/planting"
    body = {"table_ids": [1, 2], "nursery_start": str(today_bangkok())}
    env.post(url, body, 409)  # the activity is not done yet
    done = env.done(order)
    assert done["planting_ready"] is True and done["order_line_id"] == line["id"]
    with env.Session() as db:
        assert db.scalars(select(CropCycle)).all() == []
    assert env.get(url)["can_create"] is True
    created = env.post(url, body)
    assert len(created["cycle_ids"]) == 2
    line = env.get(f"/sales-orders/{order['id']}")["lines"][0]
    assert line["planting_status"] == "planted" and line["cycle_ids"] == created["cycle_ids"]
    env.post(url, {**body, "table_ids": [3]}, 409)  # no duplicates
    with env.Session() as db:
        titles = [task.title for task in db.scalars(select(Task).where(Task.cycle_id.is_not(None)))]
    assert len(titles) == 2 and all(title.startswith("ย้ายปลูก") for title in titles)


def test_declining_keeps_order_ready_and_undo_hides_prompt(env):
    order = env.order()
    env.done(order)
    assert env.get(f"/sales-orders/{order['id']}")["lines"][0]["planting_status"] == "ready"
    task_id = order["lines"][0]["planting_task_id"]
    assert env.patch(f"/tasks/{task_id}", {"status": "pending"})["planting_ready"] is False


def test_occupied_and_duplicate_tables_are_rejected(env):
    env.post("/crop-cycles", {"table_id": 1, "batch_id": 1, "crop_type_id": 1, "nursery_start": "2025-01-01"})
    order = env.order()
    env.done(order)
    url = f"/sales-orders/lines/{order['lines'][0]['id']}/planting"
    assert [table["id"] for table in env.get(url)["free_tables"]] == [2, 3]
    env.post(url, {"table_ids": [1, 2], "nursery_start": str(today_bangkok())}, 409)
    env.post(url, {"table_ids": [2, 2], "nursery_start": str(today_bangkok())}, 422)
    with env.Session() as db:
        assert db.scalars(select(SalesOrderCycle)).all() == []


def test_tables_needed_uses_harvest_history_only(env):
    assert env.order()["lines"][0]["tables_needed"] is None
    env.post("/crop-cycles", {
        "table_id": 1, "batch_id": 1, "crop_type_id": 1, "nursery_start": "2025-01-01",
        "status": "harvested", "harvest_quantity_kg": 10,
    })
    order = env.order()
    assert order["lines"][0]["tables_needed"] == 3
    env.done(order)
    assert env.get(f"/sales-orders/lines/{order['lines'][0]['id']}/planting")["suggested_table_ids"] == [1, 2, 3]


def test_edit_moves_task_and_removes_line_task(env):
    order = env.order()
    line = order["lines"][0]
    new_date = today_bangkok() + timedelta(days=70)
    item = {"id": line["id"], "product_id": env.product, "quantity": 30, "delivery_date": str(new_date)}
    edited = env.patch(f"/sales-orders/{order['id']}", {"lines": [item]})
    assert edited["lines"][0]["planting_task_id"] == line["planting_task_id"]
    assert env.get("/tasks")[0]["due_date"] == str(new_date - timedelta(days=42))
    env.patch(f"/sales-orders/{order['id']}", {"lines": [{**item, "id": None}]})
    assert len(env.get("/tasks")) == 1


def test_planted_line_cannot_be_removed_or_change_product(env):
    order = env.order()
    env.done(order)
    line = order["lines"][0]
    env.post(f"/sales-orders/lines/{line['id']}/planting", {"table_ids": [1], "nursery_start": str(today_bangkok())})
    other = env.post("/products", {"category": "vegetable", "name": "อื่น", "unit": "kg"})["id"]
    item = {"product_id": env.product, "quantity": 1, "delivery_date": line["delivery_date"]}
    env.patch(f"/sales-orders/{order['id']}", {"lines": [item]}, 409)
    env.patch(f"/sales-orders/{order['id']}", {"lines": [{**item, "id": line["id"], "product_id": other}]}, 409)


@pytest.mark.parametrize("status", ["delivered", "cancelled"])
def test_closing_removes_pending_task_and_locks_order(env, status):
    order = env.order()
    assert env.post(f"/sales-orders/{order['id']}/close", {"status": status}, 200)["status"] == status
    assert env.get("/tasks") == []
    env.patch(f"/sales-orders/{order['id']}", {"safety_days": 1}, 409)
    env.post(f"/sales-orders/{order['id']}/close", {"status": "cancelled"}, 409)


def test_unmapped_product_gets_plan_when_mapping_is_added(env):
    env.map_crop(None)
    order = env.order()
    assert order["lines"][0]["planting_status"] == "unmapped" and env.get("/tasks") == []
    env.map_crop()
    assert env.get(f"/sales-orders/{order['id']}")["lines"][0]["planting_status"] == "waiting"
    assert len(env.get("/tasks")) == 1


def test_non_crop_product_needs_no_planting(env):
    product = env.post("/products", {"category": "fertilizer", "name": "ปุ๋ยผสม", "unit": "kg"})["id"]
    order = env.order(lines=[{"product_id": product, "quantity": 1, "delivery_date": str(today_bangkok())}])
    assert order["lines"][0]["planting_status"] == "not_required" and env.get("/tasks") == []


def test_invalid_order_leaves_nothing_behind(env):
    good = {"product_id": env.product, "quantity": 1, "delivery_date": str(today_bangkok() + timedelta(days=60))}
    for bad in ({**good, "product_id": 999}, {**good, "unit": "ml"}, {**good, "quantity": 0},
                {**good, "delivery_date": str(today_bangkok() - timedelta(days=1))}):
        env.order(status=422, lines=[good, bad])
    env.order(status=422, customer_id=999)
    assert env.get("/sales-orders")["total"] == 0 and env.get("/tasks") == []


def test_sensitive_fields_are_encrypted_and_masked(env):
    order = env.order(delivery_location="ที่อยู่ลับ", note="โน้ตลับ")
    assert (order["customer_name"], order["delivery_location"], order["note"]) == ("ลูกค้าลับ", "ที่อยู่ลับ", "โน้ตลับ")
    with env.engine.connect() as connection:
        raw = str(connection.execute(text("SELECT * FROM sales_orders")).all())
    assert "ลับ" not in raw
    env.role = Role.developer
    response = env.client.get(f"/sales-orders/{order['id']}")
    assert "ลับ" not in response.text and response.json()["is_masked"] is True


def test_requires_login():
    app.dependency_overrides.clear()
    assert TestClient(app).get("/sales-orders").status_code in (401, 403)
