"""Phase 3 step 2: activities record farm work and drive stock and expenses."""
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, inspect, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.migrations import migrate_input_product_mapping
from app.models import (
    Activity, ActivityItem, Batch, ChangeNote, CropCycle, CropType, FinanceEntry, Role, StockMovement, Table, User,
)
from app.security import get_current_user
from app.services.products_stock import on_hand
from app.services.secure_fields import decrypt_number
from app.services.source_types import ACTIVITY, TASK


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
            User(id=2, username="dev", password_hash="unused", role=Role.developer),
            Table(id=1, table_number=1),
            Table(id=2, table_number=2),
            Batch(id=1, batch_number=1, start_date=date(2025, 1, 1)),
            CropType(id=1, name="Green Oak", nursery_days=14, growth_days=30),
            CropCycle(id=1, table_id=1, batch_id=1, crop_type_id=1, nursery_start=date(2025, 1, 1), cycle_code="250101", plant_count=150),
            CropCycle(id=2, table_id=2, batch_id=1, crop_type_id=1, nursery_start=date(2025, 1, 1), cycle_code="250101", plant_count=50),
        ])
        db.commit()
    return engine, Session


class API:
    def __init__(self, Session, user_id=1):
        self.Session = Session
        self.user_id = user_id

    def __enter__(self):
        def override_db():
            with self.Session() as db:
                yield db

        role = Role.owner if self.user_id == 1 else Role.developer
        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_current_user] = lambda: User(id=self.user_id, username="u", password_hash="x", role=role)
        self.client = TestClient(app)
        return self.client

    def __exit__(self, *_):
        app.dependency_overrides.clear()


def add_product(client, unit="kg", name=None):
    response = client.post("/products", json={"category": "fertilizer", "name": name or f"Input Product {unit}", "unit": unit})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def record(client, item_name="Fertilizer A", quantity=2, unit="kg", product_id=None, cycle_ids=(1,), **extra):
    item = {"item_name": item_name, "quantity": quantity, "unit": unit}
    if product_id != "OMIT":
        item["product_id"] = product_id
    body = {"kind": "fertilize", "done_on": "2025-02-01", "cycle_ids": list(cycle_ids), "items": [item], **extra}
    return client.post("/activities", json=body)


def movements(Session):
    with Session() as db:
        return db.scalars(select(StockMovement).where(StockMovement.source_type == ACTIVITY).order_by(StockMovement.id)).all()


def test_input_mapping_migration_is_additive_and_idempotent():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE products (id INTEGER PRIMARY KEY)")
        connection.exec_driver_sql("CREATE TABLE input_items (id INTEGER PRIMARY KEY, name TEXT)")
        connection.exec_driver_sql("CREATE TABLE input_catalog (id INTEGER PRIMARY KEY, name TEXT)")
    migrate_input_product_mapping(engine)
    migrate_input_product_mapping(engine)
    assert {column["name"] for column in inspect(engine).get_columns("input_catalog")} == {"id", "name", "product_id"}


# Stock -----------------------------------------------------------------------

def test_finished_activity_deducts_stock_on_its_date_and_remembers_the_link():
    _, Session = make_db()
    with API(Session) as client:
        product_id = add_product(client)
        response = record(client, product_id=product_id)
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["status"] == "done" and body["done_on"] == "2025-02-01" and body["planned_date"] == "2025-02-01"
        assert body["remind"] is False
        assert body["items"][0]["product_id"] == product_id
        [movement] = movements(Session)
        assert (movement.source_id, movement.movement_type, movement.quantity_delta) == (body["id"], "application", -2)
        assert movement.occurred_at.date() == date(2025, 1, 31)  # Bangkok midnight in UTC
        second = record(client, quantity=1, product_id="OMIT")
        assert second.json()["items"][0]["product_id"] == product_id
        with Session() as db:
            assert on_hand(db, product_id) == -3


def test_planned_and_in_progress_activities_leave_stock_alone_until_done():
    _, Session = make_db()
    with API(Session) as client:
        product_id = add_product(client)
        planned = record(client, product_id=product_id, status="pending", done_on=None, planned_date="2025-03-01")
        assert planned.status_code == 201, planned.text
        body = planned.json()
        assert (body["status"], body["remind"], body["done_on"]) == ("pending", True, None)
        assert movements(Session) == []

        started = client.post(f"/activities/{body['id']}/status", json={"status": "in_progress", "on_date": "2025-03-01"})
        assert started.json()["started_on"] == "2025-03-01"
        assert movements(Session) == []

        done = client.post(f"/activities/{body['id']}/status", json={"status": "done", "on_date": "2025-03-02"})
        assert done.json()["done_on"] == "2025-03-02"
        assert [m.quantity_delta for m in movements(Session) if m.voided_at is None] == [-2]

        back = client.post(f"/activities/{body['id']}/status", json={"status": "pending", "reason": "ยังไม่ได้ใส่จริง"})
        assert back.json()["done_on"] is None
        assert all(m.voided_at is not None for m in movements(Session))
        with Session() as db:
            assert on_hand(db, product_id) == 0


def test_editing_items_or_date_replaces_the_deduction_and_saving_unchanged_keeps_it():
    _, Session = make_db()
    with API(Session) as client:
        product_id = add_product(client)
        activity_id = record(client, product_id=product_id).json()["id"]
        assert client.patch(f"/activities/{activity_id}", json={"note": "ไม่เปลี่ยนจำนวน"}).status_code == 200
        assert len(movements(Session)) == 1

        response = client.patch(f"/activities/{activity_id}", json={"items": [
            {"item_name": "Fertilizer A", "quantity": 3.5, "unit": "kg", "product_id": product_id},
        ]})
        assert response.status_code == 200, response.text
        client.patch(f"/activities/{activity_id}", json={"done_on": "2025-02-05"})
        rows = movements(Session)
        active = [m for m in rows if m.voided_at is None]
        assert len(rows) == 3 and len(active) == 1
        assert active[0].quantity_delta == -3.5 and active[0].occurred_at.date() == date(2025, 2, 4)


def test_delete_cancels_stock_and_expenses():
    _, Session = make_db()
    with API(Session) as client:
        product_id = add_product(client)
        activity_id = record(client, product_id=product_id, labor_cost="200").json()["id"]
        assert client.delete(f"/activities/{activity_id}").status_code == 204
        assert client.get(f"/activities/{activity_id}").status_code == 404
        assert all(m.voided_at is not None for m in movements(Session))
        with Session() as db:
            assert db.scalar(select(FinanceEntry.status).where(FinanceEntry.source_type == TASK)) == "void"
            assert on_hand(db, product_id) == 0


def test_units_convert_and_mismatches_warn_without_moving_stock():
    _, Session = make_db()
    with API(Session) as client:
        product_id = add_product(client, "kg")
        assert record(client, quantity=2000, unit="g", product_id=product_id).status_code == 201
        mismatch = record(client, unit="l", product_id=product_id)
        assert mismatch.status_code == 201
        assert mismatch.json()["warnings"] == [f"unit_mismatch:{product_id}"]
        unlinked = record(client, item_name="น้ำหมัก", product_id=None)
        assert unlinked.json()["warnings"] == []
        with Session() as db:
            assert on_hand(db, product_id) == -2
            assert len(db.scalars(select(ActivityItem)).all()) == 3


def test_explicit_null_clears_the_remembered_stock_link():
    _, Session = make_db()
    with API(Session) as client:
        product_id = add_product(client)
        record(client, product_id=product_id)
        record(client, product_id=None)
        response = record(client, product_id="OMIT")
        assert response.json()["items"][0]["product_id"] is None
        with Session() as db:
            assert on_hand(db, product_id) == -2


def test_invalid_references_are_rejected_without_saving():
    _, Session = make_db()
    with API(Session) as client:
        assert record(client, product_id=9999).status_code == 422
        assert record(client, cycle_ids=(99,)).status_code == 404
        assert record(client, cycle_ids=(1, 1)).status_code == 422
        assert client.post("/activities", json={"kind": "harvest", "done_on": "2025-02-01"}).status_code == 422
        assert client.post("/activities", json={"kind": "general", "status": "pending"}).status_code == 422
        with Session() as db:
            assert db.scalar(select(Activity.id)) is None


def test_failure_while_syncing_rolls_everything_back(monkeypatch):
    _, Session = make_db()
    with API(Session) as client:
        product_id = add_product(client)

        def fail(*_args, **_kwargs):
            raise RuntimeError("injected activity sync failure")

        import app.routers.activities as router_module

        monkeypatch.setattr(router_module, "sync_activity", fail)
        with pytest.raises(RuntimeError, match="injected activity sync failure"):
            record(client, product_id=product_id)
        with Session() as db:
            assert db.scalar(select(Activity.id)) is None
            assert db.scalar(select(StockMovement.id)) is None


def test_activities_require_authentication():
    _, Session = make_db()
    with API(Session) as client:
        app.dependency_overrides.pop(get_current_user, None)
        assert record(client).status_code == 401
        assert client.get("/activities").status_code == 401


# Several tables at once --------------------------------------------------------

def test_shares_follow_plant_counts_and_split_labor_per_cycle():
    _, Session = make_db()
    with API(Session) as client:
        response = record(client, cycle_ids=(1, 2), labor_cost="301", worker_count=2)
        assert response.status_code == 201, response.text
        shares = {target["crop_cycle_id"]: target["share"] for target in response.json()["targets"]}
        assert shares == {1: 0.75, 2: 0.25}  # 150 and 50 plants
        assert {t["table_number"] for t in response.json()["targets"]} == {1, 2}
        with Session() as db:
            entries = db.scalars(select(FinanceEntry).where(FinanceEntry.status == "posted").order_by(FinanceEntry.crop_cycle_id)).all()
            assert [(e.crop_cycle_id, decrypt_number(e.amount_encrypted)) for e in entries] == [
                (1, Decimal("225.75")), (2, Decimal("75.25")),
            ]
            assert all(e.entry_date == date(2025, 2, 1) for e in entries)
            assert db.get(Activity, response.json()["id"]).cycle_id is None


def test_owner_can_fix_one_share_and_the_rest_is_split():
    _, Session = make_db()
    with API(Session) as client:
        response = record(client, cycle_ids=(1, 2), shares=[{"crop_cycle_id": 2, "share": 0.5}])
        targets = {t["crop_cycle_id"]: (t["share"], t["share_is_manual"]) for t in response.json()["targets"]}
        assert targets == {1: (0.5, False), 2: (0.5, True)}
        assert record(client, cycle_ids=(1, 2), shares=[{"crop_cycle_id": 2, "share": 1.0}, {"crop_cycle_id": 1, "share": 0.5}]).status_code == 422


def test_cleanup_can_name_a_table_without_a_crop_cycle():
    _, Session = make_db()
    with API(Session) as client:
        response = client.post("/activities", json={"kind": "cleanup", "done_on": "2025-02-01", "table_ids": [2]})
        assert response.status_code == 201, response.text
        assert response.json()["title"] == "ล้างโต๊ะ"
        assert response.json()["targets"] == [{
            "crop_cycle_id": None, "table_id": 2, "table_number": 2, "cycle_code": None,
            "crop_name": None, "share": None, "share_is_manual": False,
        }]
        assert [a["id"] for a in client.get("/activities?table_id=2").json()] == [response.json()["id"]]


def test_deleting_a_cycle_keeps_shared_activities_for_the_other_cycle():
    _, Session = make_db()
    with API(Session) as client:
        shared = record(client, cycle_ids=(1, 2), labor_cost="100").json()["id"]
        alone = record(client, cycle_ids=(2,)).json()["id"]
        assert client.delete("/crop-cycles/2").status_code == 204
        kept = client.get(f"/activities/{shared}").json()
        assert [t["crop_cycle_id"] for t in kept["targets"]] == [1]
        assert kept["targets"][0]["share"] == 1.0
        assert client.get(f"/activities/{alone}").status_code == 404
        with Session() as db:
            [entry] = db.scalars(select(FinanceEntry).where(FinanceEntry.status == "posted")).all()
            assert (entry.crop_cycle_id, decrypt_number(entry.amount_encrypted)) == (1, Decimal("100.00"))


# Listing, notes and masking --------------------------------------------------

def test_list_filters_by_kind_status_and_cycle():
    _, Session = make_db()
    with API(Session) as client:
        a = record(client, cycle_ids=(1,)).json()["id"]
        b = record(client, cycle_ids=(2,), kind="spray").json()["id"]
        c = client.post("/activities", json={"kind": "general", "status": "pending", "planned_date": "2025-04-01"}).json()["id"]
        ids = lambda query: [row["id"] for row in client.get(f"/activities{query}").json()]  # noqa: E731
        assert ids("") == [a, b, c]
        assert ids("?kind=spray") == [b]
        assert ids("?status=pending") == [c]
        assert ids("?cycle_id=1") == [a]
        assert ids("?from=2025-03-01") == [c]


def test_edits_after_the_fact_leave_change_notes_with_the_reason():
    _, Session = make_db()
    with API(Session) as client:
        activity_id = record(client, labor_cost="100").json()["id"]
        client.patch(f"/activities/{activity_id}", json={"labor_cost": "150", "reason": "ลืมค่ารถ"})
        client.patch(f"/activities/{activity_id}", json={"labor_cost": "150"})  # no real change
        changes = client.get(f"/activities/{activity_id}/changes").json()
        assert [(c["field"], c["old_value"], c["new_value"], c["reason"]) for c in changes] == [
            ("labor_cost", "100", "150", "ลืมค่ารถ"),
        ]
        with Session() as db:
            assert db.scalar(select(ChangeNote.user_id)) == 1


def test_system_activities_keep_their_title_and_items():
    _, Session = make_db()
    with Session() as db:
        db.add(Activity(kind="transplant", title="ย้ายปลูก โต๊ะ 1", planned_date=date(2025, 1, 15), source="auto"))
        db.commit()
    with API(Session) as client:
        assert client.patch("/activities/1", json={"title": "อื่น"}).status_code == 422
        assert client.patch("/activities/1", json={"note": "รอฝนหยุด"}).status_code == 200
        assert client.get("/activities/1").json()["title"] == "ย้ายปลูก โต๊ะ 1"


def test_developer_sees_masked_values_and_raw_rows_are_encrypted():
    _, Session = make_db()
    with API(Session) as client:
        activity_id = record(client, item_name="ปุ๋ยลับ", note="บันทึกลับ", title="งานลับ").json()["id"]
    with API(Session, user_id=2) as client:
        body = client.get(f"/activities/{activity_id}").json()
        assert body["is_masked"] is True
        assert body["title"].startswith("gAAAA") and body["note"].startswith("gAAAA")
        assert body["items"][0]["item_name"].startswith("gAAAA")
        assert body["items"][0]["quantity"].startswith("gAAAA")
        assert client.get("/input-catalog/suggestions?q=ปุ๋ย").json() == {"items": [], "is_masked": True}
    with Session() as db:
        activity = db.get(Activity, activity_id)
        assert "งานลับ" not in activity.title
        assert "บันทึกลับ".encode() not in activity.note_encrypted
        assert "ปุ๋ยลับ".encode() not in db.scalar(select(ActivityItem.item_name_encrypted))
