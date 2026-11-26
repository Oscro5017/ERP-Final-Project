from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, inspect, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.migrations import migrate_customer_area_encryption, migrate_finance_entries, migrate_task_finance_fields
from app.models import Batch, CropCycle, CropType, Customer, FinanceEntry, Role, StockDocumentLine, Supplier, Table, Task, User
from app.security import get_current_user
from app.services.secure_fields import decrypt_number, decrypt_text, encrypt_number, encrypt_text
from app.services.source_types import STOCK_DOCUMENT


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
            User(id=2, username="developer", password_hash="unused", role=Role.developer),
            Table(id=1, table_number=1),
            Batch(id=1, batch_number=1, start_date=date(2025, 1, 1)),
            CropType(id=1, name="Green Oak", nursery_days=14, growth_days=30),
            CropCycle(id=1, table_id=1, batch_id=1, crop_type_id=1, nursery_start=date(2025, 1, 1), harvest_quantity_kg=30),
            Customer(id=1, name_encrypted=encrypt_text("Customer One").encode("ascii")),
            Supplier(id=1, name_encrypted=encrypt_text("Supplier One").encode("ascii"), name_hash="supplier-hash"),
        ])
        db.commit()
    return engine, Session


class API:
    def __init__(self, Session, role=Role.owner):
        self.Session = Session
        self.role = role

    def __enter__(self):
        def override_db():
            with self.Session() as db:
                yield db

        app.dependency_overrides[get_db] = override_db
        user_id = 1 if self.role == Role.owner else 2
        app.dependency_overrides[get_current_user] = lambda: User(
            id=user_id, username=self.role.value, password_hash="unused", role=self.role
        )
        self.client = TestClient(app)
        return self.client

    def __exit__(self, *_):
        app.dependency_overrides.clear()


def add_product(client, name="Product A"):
    response = client.post("/products", json={"category": "vegetable", "name": name, "unit": "kg"})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def post_doc(client, kind="inbound", prices=True, date_value="2025-03-01", cycle_id=1):
    product_id = add_product(client, f"Product {kind}")
    line = {"product_id": product_id, "quantity": 2, "unit": "kg"}
    if prices:
        line["unit_price"] = 100
    payload = {"doc_date": date_value, "crop_cycle_id": cycle_id, "lines": [line]}
    response = client.post(f"/trade/{kind}", json=payload)
    assert response.status_code == 201, response.text
    return product_id, response.json()


def insert_entry(db, day, direction, category, amount, cycle_id=None, customer_id=None, supplier_id=None, is_auto=False, status="posted", source_type=None, source_id=None):
    entry = FinanceEntry(
        entry_date=day,
        direction=direction,
        category=category,
        amount_encrypted=encrypt_number(amount).encode("ascii"),
        description_encrypted=encrypt_text("finance description").encode("ascii"),
        crop_cycle_id=cycle_id,
        customer_id=customer_id,
        supplier_id=supplier_id,
        is_auto=is_auto,
        status=status,
        source_type=source_type,
        source_id=source_id,
    )
    db.add(entry)
    db.flush()
    return entry


def test_finance_migration_is_additive_and_idempotent():
    engine = create_engine("sqlite:///:memory:")
    migrate_finance_entries(engine)
    migrate_finance_entries(engine)
    assert "finance_entries" in inspect(engine).get_table_names()
    columns = {column["name"] for column in inspect(engine).get_columns("finance_entries")}
    assert {"amount_encrypted", "description_encrypted", "void_reason_encrypted", "is_auto", "source_type"} <= columns


def test_task_finance_migration_preserves_existing_task_columns_and_is_idempotent():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE tasks (id INTEGER PRIMARY KEY, title TEXT NOT NULL, status TEXT, deleted_at DATETIME)")
        connection.exec_driver_sql("INSERT INTO tasks (id, title, status) VALUES (1, 'existing', 'pending')")
    migrate_task_finance_fields(engine)
    migrate_task_finance_fields(engine)
    columns = {column["name"] for column in inspect(engine).get_columns("tasks")}
    assert {"id", "title", "labor_cost_encrypted", "worker_count", "extra_cost_encrypted", "stock_alert_product_id"} <= columns
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT title, labor_cost_encrypted FROM tasks WHERE id=1").one() == ("existing", None)


def test_customer_area_migration_is_additive_and_idempotent():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT)")
        connection.exec_driver_sql("INSERT INTO customers VALUES (1, 'existing')")
    migrate_customer_area_encryption(engine)
    migrate_customer_area_encryption(engine)
    columns = {column["name"] for column in inspect(engine).get_columns("customers")}
    assert {"id", "name", "area_encrypted"} <= columns
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT name, area_encrypted FROM customers WHERE id=1").one() == ("existing", None)


def test_inbound_document_creates_one_expense_purchase_entry_for_all_lines():
    _, Session = make_db()
    with API(Session) as client:
        p1 = add_product(client, "Product A")
        p2 = add_product(client, "Product B")
        response = client.post("/trade/inbound", json={
            "doc_date": "2025-03-01", "supplier_id": 1, "crop_cycle_id": 1,
            "lines": [
                {"product_id": p1, "quantity": 2, "unit": "kg", "unit_price": 100},
                {"product_id": p2, "quantity": 1, "unit": "kg", "unit_price": 50},
            ],
        })
        assert response.status_code == 201, response.text
        with Session() as db:
            entry = db.scalar(select(FinanceEntry).where(FinanceEntry.source_id == response.json()["id"]))
            assert entry.direction == "expense" and entry.category == "purchase" and entry.is_auto
            assert entry.source_type == STOCK_DOCUMENT
            assert entry.crop_cycle_id == 1 and entry.supplier_id == 1
            assert decrypt_number(entry.amount_encrypted) == Decimal("250.00")


def test_outbound_document_creates_income_sale_and_copies_customer_cycle_links():
    _, Session = make_db()
    with API(Session) as client:
        product_id = add_product(client)
        response = client.post("/trade/outbound", json={
            "doc_date": "2025-03-02", "customer_id": 1, "crop_cycle_id": 1,
            "lines": [{"product_id": product_id, "quantity": 2, "unit": "kg", "unit_price": 90}],
        })
        assert response.status_code == 201, response.text
        with Session() as db:
            entry = db.scalar(select(FinanceEntry).where(FinanceEntry.source_id == response.json()["id"]))
            assert (entry.direction, entry.category, entry.customer_id, entry.crop_cycle_id) == ("income", "sale", 1, 1)
            assert decrypt_number(entry.amount_encrypted) == Decimal("180.00")


def test_unpriced_document_does_not_create_finance_entry():
    _, Session = make_db()
    with API(Session) as client:
        _product_id, document = post_doc(client, prices=False)
        with Session() as db:
            assert db.scalar(select(FinanceEntry.id).where(FinanceEntry.source_id == document["id"])) is None


def test_voiding_source_document_voids_automatic_finance_entry():
    _, Session = make_db()
    with API(Session) as client:
        _product_id, document = post_doc(client)
        response = client.post(f"/trade/documents/{document['id']}/void", json={"reason": "return"})
        assert response.status_code == 200
        with Session() as db:
            entry = db.scalar(select(FinanceEntry).where(FinanceEntry.source_id == document["id"]))
            assert entry.status == "void" and entry.voided_at is not None
            assert decrypt_number(entry.amount_encrypted) == Decimal("200.00")


def test_manual_entry_is_encrypted_and_owner_can_read_plaintext():
    _, Session = make_db()
    with API(Session) as client:
        response = client.post("/finance/entries", json={
            "entry_date": "2025-04-01", "direction": "expense", "category": "utilities",
            "amount": "125.50", "description": "UTILITY_MARKER", "crop_cycle_id": 1,
        })
        assert response.status_code == 201, response.text
        assert response.json()["amount"] == "125.50"
        assert response.json()["description"] == "UTILITY_MARKER"
        with Session() as db:
            entry = db.scalar(select(FinanceEntry))
            assert b"125.50" not in entry.amount_encrypted and b"UTILITY_MARKER" not in entry.description_encrypted
            assert decrypt_number(entry.amount_encrypted) == Decimal("125.50")


def test_developer_gets_ciphertext_for_manual_entry():
    _, Session = make_db()
    with API(Session) as client:
        response = client.post("/finance/entries", json={
            "direction": "income", "category": "other", "amount": 75, "description": "PRIVATE_AMOUNT",
        })
        entry_id = response.json()["id"]
    with API(Session, Role.developer) as client:
        response = client.get(f"/finance/entries?status=posted")
        body = response.json()["items"][0]
        assert body["id"] == entry_id and body["is_masked"] is True
        assert "PRIVATE_AMOUNT" not in str(body) and body["amount"] != "75"


def test_manual_entry_requires_amount_greater_than_zero():
    _, Session = make_db()
    with API(Session) as client:
        for amount in (0, -1):
            response = client.post("/finance/entries", json={"direction": "expense", "category": "other", "amount": amount})
            assert response.status_code == 422


def test_manual_entry_rejects_missing_crop_cycle():
    _, Session = make_db()
    with API(Session) as client:
        response = client.post("/finance/entries", json={
            "direction": "expense", "category": "other", "amount": 10, "crop_cycle_id": 999,
        })
        assert response.status_code == 422


def test_manual_patch_and_void_update_encrypted_values():
    _, Session = make_db()
    with API(Session) as client:
        created = client.post("/finance/entries", json={"direction": "expense", "category": "other", "amount": 10})
        entry_id = created.json()["id"]
        updated = client.patch(f"/finance/entries/{entry_id}", json={"amount": 12.5, "category": "equipment", "description": "updated"})
        assert updated.status_code == 200 and updated.json()["amount"] == "12.50"
        voided = client.post(f"/finance/entries/{entry_id}/void", json={"reason": "correction"})
        assert voided.status_code == 200 and voided.json()["status"] == "void"
        with Session() as db:
            entry = db.get(FinanceEntry, entry_id)
            assert decrypt_number(entry.amount_encrypted) == Decimal("12.5")
            assert decrypt_text(entry.void_reason_encrypted) == "correction"


def test_automatic_entry_cannot_be_manually_edited_or_voided():
    _, Session = make_db()
    with API(Session) as client:
        _pid, document = post_doc(client)
        entry_id = document["id"]
        response = client.get("/finance/entries?from=2025-03-01&to=2025-03-01")
        finance_id = response.json()["items"][0]["id"]
        assert client.patch(f"/finance/entries/{finance_id}", json={"amount": 9}).status_code == 409
        assert client.post(f"/finance/entries/{finance_id}/void", json={}).status_code == 409
        assert client.get(f"/trade/documents/{entry_id}").status_code == 200


def test_entry_list_filters_and_pagination():
    _, Session = make_db()
    with API(Session) as client:
        for direction, category, day in (("income", "sale", "2025-03-01"), ("expense", "other", "2025-03-02")):
            assert client.post("/finance/entries", json={"entry_date": day, "direction": direction, "category": category, "amount": 10}).status_code == 201
        response = client.get("/finance/entries?from=2025-03-01&to=2025-03-01&direction=income&category=sale&limit=1")
        assert response.status_code == 200 and response.json()["total"] == 1 and len(response.json()["items"]) == 1


def test_summary_aggregates_income_expense_profit_and_unallocated_expense():
    _, Session = make_db()
    with Session() as db:
        insert_entry(db, date(2025, 3, 1), "income", "sale", 100, cycle_id=1)
        insert_entry(db, date(2025, 3, 2), "expense", "purchase", 30, cycle_id=1)
        insert_entry(db, date(2025, 3, 3), "expense", "utilities", 20)
        db.commit()
    with API(Session) as client:
        response = client.get("/finance/summary?from=2025-03-01&to=2025-03-31")
        row = response.json()["items"][0]
        assert row["key"] == "all" and row["income"]["value"] == 100
        assert row["expense"]["value"] == 50 and row["profit"]["value"] == 50
        assert row["entry_count"] == 3
        assert response.json()["unallocated_expense"]["value"] == 20


@pytest.mark.parametrize("group_by,key", [("month", "2025-03"), ("quarter", "2025-Q1"), ("season", "summer_2025"), ("category", "sale"), ("cycle", "1"), ("customer", "1")])
def test_summary_grouping_keys(group_by, key):
    _, Session = make_db()
    with Session() as db:
        insert_entry(db, date(2025, 3, 5), "income", "sale", 5, cycle_id=1, customer_id=1)
        db.commit()
    with API(Session) as client:
        response = client.get(f"/finance/summary?from=2025-01-01&to=2025-12-31&group_by={group_by}")
        assert response.status_code == 200 and response.json()["items"][0]["key"] == key


def test_summary_rejects_ranges_over_366_days_and_invalid_group():
    _, Session = make_db()
    with API(Session) as client:
        assert client.get("/finance/summary?from=2024-01-01&to=2025-01-01").status_code == 422
        assert client.get("/finance/summary?from=2025-01-01&to=2025-01-02&group_by=bogus").status_code == 422


def test_summary_masks_aggregate_for_developer():
    _, Session = make_db()
    with Session() as db:
        insert_entry(db, date(2025, 3, 5), "income", "sale", 5)
        db.commit()
    with API(Session, Role.developer) as client:
        response = client.get("/finance/summary?from=2025-03-01&to=2025-03-31")
        assert response.status_code == 200
        aggregate = response.json()["items"][0]["income"]
        assert aggregate["is_masked"] is True and aggregate["value"] != "5.00"


def test_summary_skips_invalid_ciphertexts_and_reports_count():
    _, Session = make_db()
    with Session() as db:
        db.add(FinanceEntry(entry_date=date(2025, 3, 5), direction="income", category="sale", amount_encrypted=b"bad-token", status="posted", is_auto=False))
        db.commit()
    with API(Session) as client:
        response = client.get("/finance/summary?from=2025-03-01&to=2025-03-31")
        assert response.json()["skipped_decrypt_failed"] == 1
        assert response.json()["items"] == []


def test_summary_respects_row_cap(monkeypatch):
    _, Session = make_db()
    with Session() as db:
        insert_entry(db, date(2025, 3, 1), "income", "sale", 5)
        insert_entry(db, date(2025, 3, 2), "income", "sale", 7)
        db.commit()
    import app.routers.finance as finance_router

    monkeypatch.setattr(finance_router, "_MAX_AGGREGATE_ROWS", 1)
    with API(Session) as client:
        response = client.get("/finance/summary?from=2025-03-01&to=2025-03-31")
        assert response.json()["truncated"] is True
        assert response.json()["items"][0]["income"]["value"] == 5


def test_cycle_pnl_includes_margin_cost_per_kg_and_category_totals():
    _, Session = make_db()
    with Session() as db:
        insert_entry(db, date(2025, 3, 1), "income", "sale", 300, cycle_id=1)
        insert_entry(db, date(2025, 3, 2), "expense", "purchase", 60, cycle_id=1)
        db.commit()
    with API(Session) as client:
        response = client.get("/finance/cycles/1/pnl")
        body = response.json()
        assert body["revenue"]["value"] == 300
        assert body["cost"]["value"] == 60
        assert body["profit"]["value"] == 240
        assert body["margin_pct"]["value"] == 80
        assert body["cost_per_kg"]["value"] == 2
        assert {row["category"] for row in body["categories"]} == {"sale", "purchase"}


def test_cycle_pnl_returns_null_cost_per_kg_without_harvest_quantity():
    _, Session = make_db()
    with Session() as db:
        db.get(CropCycle, 1).harvest_quantity_kg = None
        db.commit()
    with API(Session) as client:
        response = client.get("/finance/cycles/1/pnl")
        assert response.json()["cost_per_kg"] is None


def test_finance_endpoints_require_authentication():
    _, Session = make_db()
    with API(Session) as client:
        app.dependency_overrides.pop(get_current_user, None)
        assert client.get("/finance/entries").status_code == 401
        assert client.get("/finance/summary?from=2025-01-01&to=2025-01-31").status_code == 401


def test_completed_task_with_costs_creates_auto_labor_entry():
    _, Session = make_db()
    with API(Session) as client:
        response = client.post("/tasks", json={
            "title": "Harvest work", "due_date": "2025-03-01", "cycle_id": 1,
            "status": "done", "labor_cost": "100.00", "worker_count": 2, "extra_cost": "25.50",
        })
        assert response.status_code == 201, response.text
        task_id = response.json()["id"]
        with Session() as db:
            entry = db.scalar(select(FinanceEntry).where(FinanceEntry.source_type == "task", FinanceEntry.source_id == task_id))
            assert entry.direction == "expense" and entry.category == "labor" and entry.is_auto
            assert entry.crop_cycle_id == 1 and decrypt_number(entry.amount_encrypted) == Decimal("125.50")
            task = db.get(Task, task_id)
            assert b"100.00" not in task.labor_cost_encrypted


def test_pending_task_cost_only_posts_when_marked_done():
    _, Session = make_db()
    with API(Session) as client:
        response = client.post("/tasks", json={
            "title": "Pending paid work", "due_date": "2025-03-01", "cycle_id": 1,
            "labor_cost": 50,
        })
        task_id = response.json()["id"]
        with Session() as db:
            assert db.scalar(select(FinanceEntry.id).where(FinanceEntry.source_id == task_id)) is None
        assert client.patch(f"/tasks/{task_id}", json={"status": "done"}).status_code == 200
        with Session() as db:
            entry = db.scalar(select(FinanceEntry).where(FinanceEntry.source_type == "task", FinanceEntry.source_id == task_id))
            assert decrypt_number(entry.amount_encrypted) == Decimal("50.00")


def test_completed_task_cost_edit_voids_previous_entry_and_creates_replacement():
    _, Session = make_db()
    with API(Session) as client:
        task_id = client.post("/tasks", json={
            "title": "Paid work", "due_date": "2025-03-01", "cycle_id": 1,
            "status": "done", "labor_cost": 50,
        }).json()["id"]
        assert client.patch(f"/tasks/{task_id}", json={"labor_cost": 80}).status_code == 200
        with Session() as db:
            entries = db.scalars(select(FinanceEntry).where(FinanceEntry.source_type == "task", FinanceEntry.source_id == task_id).order_by(FinanceEntry.id)).all()
            assert len(entries) == 2 and entries[0].status == "void" and entries[1].status == "posted"
            assert decrypt_number(entries[1].amount_encrypted) == Decimal("80.00")


def test_marking_paid_task_pending_voids_auto_entry():
    _, Session = make_db()
    with API(Session) as client:
        task_id = client.post("/tasks", json={
            "title": "Paid work", "due_date": "2025-03-01", "status": "done", "extra_cost": 25,
        }).json()["id"]
        assert client.patch(f"/tasks/{task_id}", json={"status": "pending"}).status_code == 200
        with Session() as db:
            entry = db.scalar(select(FinanceEntry).where(FinanceEntry.source_id == task_id))
            assert entry.status == "void"


def test_worker_count_alone_creates_zero_amount_labor_entry():
    _, Session = make_db()
    with API(Session) as client:
        task_id = client.post("/tasks", json={
            "title": "Volunteer work", "due_date": "2025-03-01", "status": "done", "worker_count": 3,
        }).json()["id"]
        with Session() as db:
            entry = db.scalar(select(FinanceEntry).where(FinanceEntry.source_id == task_id))
            assert entry is not None and decrypt_number(entry.amount_encrypted) == Decimal("0.00")


def test_task_without_financial_fields_keeps_existing_behavior():
    _, Session = make_db()
    with API(Session) as client:
        task_id = client.post("/tasks", json={"title": "Normal task", "due_date": "2025-03-01", "status": "done"}).json()["id"]
        with Session() as db:
            assert db.scalar(select(FinanceEntry.id).where(FinanceEntry.source_id == task_id)) is None


def test_deleting_task_voids_its_finance_entry_and_cost_fields_are_masked_for_developer():
    _, Session = make_db()
    with API(Session) as client:
        task_id = client.post("/tasks", json={
            "title": "Private task", "due_date": "2025-03-01", "status": "done", "labor_cost": 42,
        }).json()["id"]
    with API(Session, Role.developer) as client:
        response = client.get("/tasks")
        task = next(item for item in response.json() if item["id"] == task_id)
        assert task["is_masked"] is True and task["labor_cost"] != "42.00"
        assert client.delete(f"/tasks/{task_id}").status_code == 204
    with Session() as db:
        entry = db.scalar(select(FinanceEntry).where(FinanceEntry.source_id == task_id))
        assert entry.status == "void"


def test_price_trends_calculate_weighted_average_min_max_and_quantity():
    _, Session = make_db()
    with API(Session) as client:
        product_id = add_product(client)
        for customer_id, quantity, price in ((1, 10, 90), (1, 5, 100)):
            response = client.post("/trade/outbound", json={
                "doc_date": "2025-03-12", "customer_id": customer_id,
                "lines": [{"product_id": product_id, "quantity": quantity, "unit": "kg", "unit_price": price}],
            })
            assert response.status_code == 201, response.text
        response = client.get(f"/finance/prices?product_id={product_id}&from=2025-03-01&to=2025-03-31&group_by=month")
        row = response.json()["items"][0]
        assert row["key"] == "2025-03"
        assert row["weighted_avg_price"]["value"] == 93.33
        assert row["min"]["value"] == 90 and row["max"]["value"] == 100
        assert row["line_count"] == 2 and row["total_quantity"] == 15


def test_price_trends_group_by_customer_and_reject_bad_ranges():
    _, Session = make_db()
    with API(Session) as client:
        product_id = add_product(client)
        response = client.post("/trade/outbound", json={
            "doc_date": "2025-03-12", "customer_id": 1,
            "lines": [{"product_id": product_id, "quantity": 1, "unit": "kg", "unit_price": 80}],
        })
        assert response.status_code == 201
        grouped = client.get(f"/finance/prices?from=2025-03-01&to=2025-03-31&group_by=customer")
        assert grouped.json()["items"][0]["key"] == "1"
        assert client.get("/finance/prices?from=2024-01-01&to=2025-01-01").status_code == 422
        assert client.get("/finance/prices?from=2025-01-01&to=2025-01-02&group_by=year").status_code == 422


def test_price_trends_skip_invalid_encrypted_unit_prices():
    _, Session = make_db()
    with API(Session) as client:
        product_id, document = post_doc(client, kind="outbound")
        with Session() as db:
            line = db.scalar(select(StockDocumentLine).where(StockDocumentLine.document_id == document["id"]))
            line.unit_price_encrypted = b"invalid-token"
            db.commit()
        response = client.get(f"/finance/prices?product_id={product_id}&from=2025-03-01&to=2025-03-31")
        assert response.json()["skipped_decrypt_failed"] == 1 and response.json()["items"] == []


def test_price_trend_row_cap_sets_truncated(monkeypatch):
    _, Session = make_db()
    with API(Session) as client:
        product_id = add_product(client)
        for day in ("2025-03-01", "2025-03-02"):
            response = client.post("/trade/outbound", json={
                "doc_date": day,
                "lines": [{"product_id": product_id, "quantity": 1, "unit": "kg", "unit_price": 10}],
            })
            assert response.status_code == 201
    import app.routers.finance as finance_router

    monkeypatch.setattr(finance_router, "_MAX_AGGREGATE_ROWS", 1)
    with API(Session) as client:
        response = client.get(f"/finance/prices?product_id={product_id}&from=2025-03-01&to=2025-03-31")
        assert response.json()["truncated"] is True
        assert response.json()["items"][0]["line_count"] == 1


def test_customer_revenue_totals_share_rank_and_masks_names_for_developer():
    _, Session = make_db()
    with Session() as db:
        db.add(Customer(id=2, name_encrypted=encrypt_text("Customer Two").encode("ascii")))
        db.commit()
    with API(Session) as client:
        for customer_id, amount in ((1, 100), (2, 300)):
            response = client.post("/finance/entries", json={
                "entry_date": "2025-03-01", "direction": "income", "category": "sale",
                "amount": amount, "customer_id": customer_id,
            })
            assert response.status_code == 201
    with API(Session, Role.developer) as client:
        response = client.get("/finance/customers/revenue?from=2025-03-01&to=2025-03-31")
        rows = response.json()["items"]
        assert rows[0]["customer_id"] == 2 and rows[0]["rank"] == 1
        assert rows[0]["share_pct"]["is_masked"] is True
        assert rows[0]["is_masked"] is True and "Customer Two" not in rows[0]["customer_name"]


def test_customer_revenue_ignores_expenses_and_reports_decrypt_failures():
    _, Session = make_db()
    with Session() as db:
        insert_entry(db, date(2025, 3, 1), "expense", "purchase", 400, customer_id=1)
        db.add(FinanceEntry(entry_date=date(2025, 3, 2), direction="income", category="sale", amount_encrypted=b"broken", customer_id=1, status="posted", is_auto=False))
        db.commit()
    with API(Session) as client:
        response = client.get("/finance/customers/revenue?from=2025-03-01&to=2025-03-31")
        assert response.json()["items"] == []
        assert response.json()["skipped_decrypt_failed"] == 1


def test_customer_revenue_requires_authentication():
    _, Session = make_db()
    with API(Session) as client:
        app.dependency_overrides.pop(get_current_user, None)
        assert client.get("/finance/customers/revenue?from=2025-03-01&to=2025-03-31").status_code == 401


def test_customer_area_is_encrypted_and_masked_on_customer_api():
    _, Session = make_db()
    with API(Session) as client:
        created = client.post("/customers", json={"name": "Area Customer", "contact": "", "area": "North Field"})
        assert created.status_code == 201, created.text
        customer_id = created.json()["id"]
        assert created.json()["area"] == "North Field"
        with Session() as db:
            customer = db.get(Customer, customer_id)
            assert b"North Field" not in customer.area_encrypted
        assert client.patch(f"/customers/{customer_id}", json={"area": "South Field"}).json()["area"] == "South Field"
    with API(Session, Role.developer) as client:
        body = next(row for row in client.get("/customers").json() if row["id"] == customer_id)
        assert body["is_masked"] is True and body["area"] != "South Field"


def test_summary_and_price_reports_group_by_encrypted_area():
    _, Session = make_db()
    with Session() as db:
        customer = db.get(Customer, 1)
        customer.area_encrypted = encrypt_text("North Field").encode("ascii")
        db.add(Customer(id=2, name_encrypted=encrypt_text("Customer Two").encode("ascii"), area_encrypted=encrypt_text("North Field").encode("ascii")))
        insert_entry(db, date(2025, 3, 1), "income", "sale", 100, customer_id=1)
        insert_entry(db, date(2025, 3, 2), "income", "sale", 50, customer_id=2)
        db.commit()
    with API(Session) as client:
        summary = client.get("/finance/summary?from=2025-03-01&to=2025-03-31&group_by=area").json()
        assert len(summary["items"]) == 1
        assert summary["items"][0]["key"] == "North Field"
        assert summary["items"][0]["income"]["value"] == 150
        product_id = add_product(client)
        for customer_id, price in ((1, 90), (2, 100)):
            response = client.post("/trade/outbound", json={
                "doc_date": "2025-03-10", "customer_id": customer_id,
                "lines": [{"product_id": product_id, "quantity": 1, "unit": "kg", "unit_price": price}],
            })
            assert response.status_code == 201
        prices = client.get(f"/finance/prices?product_id={product_id}&from=2025-03-01&to=2025-03-31&group_by=area").json()
        assert len(prices["items"]) == 1
        assert prices["items"][0]["key"] == "North Field"
        assert prices["items"][0]["weighted_avg_price"]["value"] == 95


def test_area_grouping_masks_area_key_for_developer():
    _, Session = make_db()
    with Session() as db:
        db.get(Customer, 1).area_encrypted = encrypt_text("Secret Farm Area").encode("ascii")
        insert_entry(db, date(2025, 3, 1), "income", "sale", 100, customer_id=1)
        db.commit()
    with API(Session, Role.developer) as client:
        row = client.get("/finance/summary?from=2025-03-01&to=2025-03-31&group_by=area").json()["items"][0]
        assert row["is_masked"] is True and row["key"] != "Secret Farm Area"
