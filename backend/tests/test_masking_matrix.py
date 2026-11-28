import re
from datetime import date, datetime
from decimal import Decimal
import json
import asyncio
import logging

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import (
    Batch, CropCycle, CropCycleStatusLog, CropType, Customer, FinanceEntry,
    ActivityItem, ActivityTarget, InputCatalog, Insight, Product,
    Role, StockDocument, StockDocumentLine, StockMovement, Supplier, Table, Activity, User,
)
from app.security import get_current_user
from app.services.secure_fields import encrypt_number, encrypt_text, hash_catalog_name


MARKERS = {
    "ZZ_PRODUCT_SECRET_6F92", "ZZ_MOVEMENT_NOTE_6F92", "ZZ_SUPPLIER_NAME_6F92",
    "ZZ_SUPPLIER_CONTACT_6F92", "ZZ_SUPPLIER_AREA_6F92", "ZZ_SUPPLIER_NOTE_6F92",
    "ZZ_CUSTOMER_NAME_6F92", "ZZ_CUSTOMER_CONTACT_6F92", "ZZ_CUSTOMER_AREA_6F92",
    "ZZ_DOCUMENT_NOTE_6F92", "ZZ_INPUT_NAME_6F92", "ZZ_INPUT_NOTE_6F92", "ZZ_INPUT_TITLE_6F92",
    "ZZ_TASK_TITLE_6F92", "ZZ_FINANCE_DESCRIPTION_6F92", "ZZ_INSIGHT_TITLE_6F92",
    "ZZ_INSIGHT_BODY_6F92", "98765.43", "12345.67", "54321.09", "55.55",
    "123.45", "234.56", "345.67", "456.78",
}


def _enc(value):
    return encrypt_text(value).encode("ascii")


def _make_phase2_db():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )

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
            Batch(id=1, batch_number=1, start_date=date(2026, 1, 1), week_offset=0),
            Product(
                id=1, category="vegetable", name_encrypted=_enc("ZZ_PRODUCT_SECRET_6F92"),
                name_hash=hash_catalog_name("ZZ_PRODUCT_SECRET_6F92"), unit="kg", is_active=True,
            ),
        ])
        db.flush()
        db.add(CropType(id=1, name="Green Oak", nursery_days=14, growth_days=30, product_id=1))
        db.flush()
        db.add(CropCycle(
            id=1, table_id=1, batch_id=1, crop_type_id=1, nursery_start=date(2026, 1, 1),
            status="nursery", cycle_code="260101", harvest_quantity_kg=30,
        ))
        db.add(CropCycleStatusLog(id=1, cycle_id=1, from_status=None, to_status="nursery", changed_at=datetime(2026, 1, 1)))
        db.add_all([
            Customer(
                id=1, name_encrypted=_enc("ZZ_CUSTOMER_NAME_6F92"),
                contact_encrypted=_enc("ZZ_CUSTOMER_CONTACT_6F92"),
                area_encrypted=_enc("ZZ_CUSTOMER_AREA_6F92"),
            ),
            Supplier(
                id=1, name_encrypted=_enc("ZZ_SUPPLIER_NAME_6F92"),
                name_hash=hash_catalog_name("ZZ_SUPPLIER_NAME_6F92"),
                contact_encrypted=_enc("ZZ_SUPPLIER_CONTACT_6F92"),
                area_encrypted=_enc("ZZ_SUPPLIER_AREA_6F92"),
                note_encrypted=_enc("ZZ_SUPPLIER_NOTE_6F92"), is_active=True,
            ),
            StockMovement(
                id=1, product_id=1, quantity_delta=30, movement_type="receipt",
                occurred_at=datetime(2026, 11, 1), note_encrypted=_enc("ZZ_MOVEMENT_NOTE_6F92"),
            ),
            StockDocument(
                id=1, doc_no="OUT-261101-001", doc_type="outbound", doc_date=date(2026, 11, 1),
                customer_id=1, crop_cycle_id=1, note_encrypted=_enc("ZZ_DOCUMENT_NOTE_6F92"),
                status="posted",
            ),
            Activity(
                id=2, kind="fertilize", cycle_id=1, title=_enc("ZZ_INPUT_TITLE_6F92").decode("ascii"),
                planned_date=date(2026, 11, 1), done_on=date(2026, 11, 1), status="done", source="manual",
                is_encrypted=True, note_encrypted=_enc("ZZ_INPUT_NOTE_6F92"),
            ),
            InputCatalog(
                id=1, name_encrypted=_enc("ZZ_INPUT_NAME_6F92"),
                name_hash=hash_catalog_name("ZZ_INPUT_NAME_6F92"), last_unit="kg",
                last_category="fertilizer", use_count=1, product_id=1,
            ),
            FinanceEntry(
                id=1, entry_date=date.today(), direction="income", category="sale",
                amount_encrypted=encrypt_number(Decimal("98765.43")).encode("ascii"),
                description_encrypted=_enc("ZZ_FINANCE_DESCRIPTION_6F92"),
                source_type="stock_document", source_id=1, crop_cycle_id=1, customer_id=1,
                is_auto=True, status="posted",
            ),
            Activity(
                id=1, cycle_id=1, title=_enc("ZZ_TASK_TITLE_6F92").decode("ascii"),
                planned_date=date.today(), status="pending", source="manual", is_encrypted=True,
                labor_cost_encrypted=encrypt_number(Decimal("12345.67")).encode("ascii"),
                worker_count=2, extra_cost_encrypted=encrypt_number(Decimal("54321.09")).encode("ascii"),
            ),
            Insight(
                id=1, kind="insight", source="rule", title_encrypted=_enc("ZZ_INSIGHT_TITLE_6F92"),
                body_encrypted=_enc("ZZ_INSIGHT_BODY_6F92"), severity="info", status="new",
            ),
        ])
        db.add(ActivityItem(
            id=1, activity_id=2, item_name_encrypted=_enc("ZZ_INPUT_NAME_6F92"),
            quantity_encrypted=encrypt_number(Decimal("98765.43")).encode("ascii"), unit="kg", product_id=1,
        ))
        db.add(ActivityTarget(activity_id=2, crop_cycle_id=1, table_id=1, share=1.0))
        db.add(StockDocumentLine(
            id=1, document_id=1, line_no=1, product_id=1, quantity=1, unit="kg",
            unit_price_encrypted=encrypt_number(Decimal("54321.09")).encode("ascii"),
            line_amount_encrypted=encrypt_number(Decimal("54321.09")).encode("ascii"),
        ))
        db.commit()
    return engine, Session


def _client(Session, role):
    def override_db():
        with Session() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    if role is None:
        app.dependency_overrides.pop(get_current_user, None)
    else:
        user_id = 1 if role == Role.owner else 2
        app.dependency_overrides[get_current_user] = lambda: User(
            id=user_id, username=role.value, password_hash="unused", role=role
        )
    return TestClient(app)


READ_ENDPOINTS = [
    "/crop-types", "/crop-cycles", "/crop-cycles/1/status-log", "/dashboard/summary",
    "/customers", "/finance/entries", "/finance/summary?from=2026-01-01&to=2026-12-31",
    "/finance/cycles/1/pnl", "/finance/prices?from=2026-01-01&to=2026-12-31",
    "/finance/customers/revenue?from=2026-01-01&to=2026-12-31", "/insights", "/insights/1",
    "/activities", "/activities/2", "/input-catalog/suggestions", "/products",
    "/products/1/movements", "/suppliers", "/suppliers/1", "/stock/balances",
    "/stock/movements", "/trade/documents", "/trade/documents/1", "/tasks",
]

WRITE_ENDPOINTS = [
    ("PATCH", "/crop-types/1/product-mapping", {"product_id": 1}),
    ("POST", "/crop-cycles", {"table_id": 1, "batch_id": 1, "crop_type_id": 1, "nursery_start": "2026-02-01"}),
    ("PATCH", "/crop-cycles/1", {"harvest_quantity_kg": 30}),
    ("DELETE", "/crop-cycles/1", None),
    ("POST", "/customers", {"name": "ZZ_MATRIX_CUSTOMER_6F92", "contact": "ZZ_MATRIX_CONTACT_6F92", "area": "ZZ_MATRIX_AREA_6F92"}),
    ("PATCH", "/customers/1", {"area": "ZZ_MATRIX_AREA_UPDATED_6F92"}),
    ("DELETE", "/customers/1", None),
    ("POST", "/finance/entries", {"entry_date": "2026-11-01", "direction": "expense", "category": "other", "amount": "98765.43", "description": "ZZ_MATRIX_FINANCE_6F92"}),
    ("PATCH", "/finance/entries/1", {"description": "ZZ_MATRIX_FINANCE_UPDATED_6F92"}),
    ("POST", "/finance/entries/1/void", {"reason": "ZZ_MATRIX_VOID_FINANCE_6F92"}),
    ("PATCH", "/insights/1/status", {"status": "seen"}),
    ("POST", "/activities", {"kind": "fertilize", "cycle_ids": [1], "note": "ZZ_MATRIX_INPUT_NOTE_6F92", "items": [{"item_name": "ZZ_MATRIX_INPUT_6F92", "quantity": 1, "unit": "kg"}]}),
    ("PATCH", "/activities/2", {"note": "ZZ_MATRIX_INPUT_UPDATED_6F92", "reason": "ZZ_MATRIX_REASON_6F92"}),
    ("POST", "/activities/2/status", {"status": "pending"}),
    ("DELETE", "/activities/2", None),
    ("POST", "/products", {"category": "other", "name": "ZZ_MATRIX_PRODUCT_6F92", "unit": "kg"}),
    ("PATCH", "/products/1", {"name": "ZZ_MATRIX_PRODUCT_UPDATED_6F92"}),
    ("POST", "/products/1/adjustments", {"counted_quantity": 7, "unit": "kg", "note": "ZZ_MATRIX_ADJUSTMENT_6F92"}),
    ("DELETE", "/products/1", None),
    ("POST", "/suppliers", {"name": "ZZ_MATRIX_SUPPLIER_6F92", "contact": "ZZ_MATRIX_SUPPLIER_CONTACT_6F92", "area": "ZZ_MATRIX_SUPPLIER_AREA_6F92", "note": "ZZ_MATRIX_SUPPLIER_NOTE_6F92"}),
    ("PATCH", "/suppliers/1", {"note": "ZZ_MATRIX_SUPPLIER_UPDATED_6F92"}),
    ("DELETE", "/suppliers/1", None),
    ("POST", "/trade/inbound", {"supplier_id": 1, "note": "ZZ_MATRIX_INBOUND_6F92", "lines": [{"product_id": 1, "quantity": 1, "unit": "kg", "unit_price": "123.45"}]}),
    ("POST", "/trade/outbound", {"customer_id": 1, "note": "ZZ_MATRIX_OUTBOUND_6F92", "lines": [{"product_id": 1, "quantity": 1, "unit": "kg", "unit_price": "234.56"}]}),
    ("PATCH", "/trade/documents/1", {"note": "ZZ_MATRIX_DOCUMENT_UPDATED_6F92"}),
    ("POST", "/trade/documents/1/void", {"reason": "ZZ_MATRIX_VOID_DOCUMENT_6F92"}),
    ("POST", "/tasks", {"title": "ZZ_MATRIX_TASK_6F92", "due_date": "2026-11-01", "labor_cost": "345.67", "worker_count": 2, "extra_cost": "456.78"}),
    ("PATCH", "/tasks/1", {"title": "ZZ_MATRIX_TASK_UPDATED_6F92"}),
    ("DELETE", "/tasks/1", None),
]


def test_phase2_read_endpoint_masking_matrix_covers_auth_owner_and_developer(caplog):
    engine, Session = _make_phase2_db()
    try:
        app.dependency_overrides.clear()

        def override_db():
            with Session() as db:
                yield db

        app.dependency_overrides[get_db] = override_db
        async def run_matrix():
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                for role in (None, Role.owner, Role.developer):
                    if role is None:
                        app.dependency_overrides.pop(get_current_user, None)
                    else:
                        user_id = 1 if role == Role.owner else 2
                        app.dependency_overrides[get_current_user] = lambda user_id=user_id, role=role: User(
                            id=user_id, username=role.value, password_hash="unused", role=role
                        )
                    for path in READ_ENDPOINTS:
                        response = await client.get(path)
                        if role is None:
                            assert response.status_code == 401, path
                        else:
                            assert response.status_code == 200, (path, response.text)
                            if role == Role.developer:
                                body = json.dumps(response.json(), ensure_ascii=False)
                                assert not any(marker in body for marker in MARKERS), (path, body)
                                if path in ("/products", "/suppliers", "/suppliers/1", "/trade/documents/1", "/finance/entries", "/insights/1"):
                                    assert "is_masked" in body, (path, body)

        asyncio.run(run_matrix())
        log_text = "\n".join(record.getMessage() for record in caplog.records)
        assert not any(marker in log_text for marker in MARKERS)
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_phase2_write_endpoint_responses_mask_owner_and_developer_matrix():
    marker_values = MARKERS | {
        "ZZ_MATRIX_CUSTOMER_6F92", "ZZ_MATRIX_CONTACT_6F92", "ZZ_MATRIX_AREA_6F92",
        "ZZ_MATRIX_AREA_UPDATED_6F92", "ZZ_MATRIX_FINANCE_6F92", "ZZ_MATRIX_FINANCE_UPDATED_6F92",
        "ZZ_MATRIX_VOID_FINANCE_6F92", "ZZ_MATRIX_INPUT_NOTE_6F92", "ZZ_MATRIX_INPUT_6F92",
        "ZZ_MATRIX_INPUT_UPDATED_6F92", "ZZ_MATRIX_PRODUCT_6F92", "ZZ_MATRIX_PRODUCT_UPDATED_6F92",
        "ZZ_MATRIX_ADJUSTMENT_6F92", "ZZ_MATRIX_SUPPLIER_6F92", "ZZ_MATRIX_SUPPLIER_CONTACT_6F92",
        "ZZ_MATRIX_SUPPLIER_AREA_6F92", "ZZ_MATRIX_SUPPLIER_NOTE_6F92", "ZZ_MATRIX_SUPPLIER_UPDATED_6F92",
        "ZZ_MATRIX_INBOUND_6F92", "ZZ_MATRIX_OUTBOUND_6F92", "ZZ_MATRIX_DOCUMENT_UPDATED_6F92",
        "ZZ_MATRIX_VOID_DOCUMENT_6F92", "ZZ_MATRIX_TASK_6F92", "ZZ_MATRIX_TASK_UPDATED_6F92",
    }

    # All write routes first reject a valid unauthenticated request.
    engine, Session = _make_phase2_db()
    try:
        client = _client(Session, None)
        for method, path, payload in WRITE_ENDPOINTS:
            response = client.request(method, path, json=payload)
            assert response.status_code == 401, (method, path, response.status_code, response.text)
    finally:
        app.dependency_overrides.clear()
        engine.dispose()

    # Then exercise every response-bearing write for owner and developer. The
    # developer response body must never contain any supplied or seeded marker.
    for role in (Role.owner, Role.developer):
        engine, Session = _make_phase2_db()
        try:
            client = _client(Session, role)

            def send(method, path, payload=None):
                response = client.request(method, path, json=payload)
                assert response.status_code in {200, 201, 204}, (
                    role.value, method, path, response.status_code, response.text
                )
                if role == Role.developer:
                    # Timestamps can contain digits like "55.55"; only data fields matter here.
                    body = re.sub(r"\d{4}-\d{2}-\d{2}T[\d:.]+", "", response.text)
                    assert not any(marker in body for marker in marker_values), (
                        method, path, response.text
                    )
                return response

            # Product/supplier/customer CRUD responses.
            product_id = send("POST", "/products", {
                "category": "other", "name": "ZZ_MATRIX_PRODUCT_6F92", "unit": "kg",
            }).json()["id"]
            send("PATCH", f"/products/{product_id}", {"name": "ZZ_MATRIX_PRODUCT_UPDATED_6F92"})
            send("POST", f"/products/{product_id}/adjustments", {
                "counted_quantity": 7, "unit": "kg", "note": "ZZ_MATRIX_ADJUSTMENT_6F92",
            })
            supplier_id = send("POST", "/suppliers", {
                "name": "ZZ_MATRIX_SUPPLIER_6F92", "contact": "ZZ_MATRIX_SUPPLIER_CONTACT_6F92",
                "area": "ZZ_MATRIX_SUPPLIER_AREA_6F92", "note": "ZZ_MATRIX_SUPPLIER_NOTE_6F92",
            }).json()["id"]
            send("PATCH", f"/suppliers/{supplier_id}", {"note": "ZZ_MATRIX_SUPPLIER_UPDATED_6F92"})
            customer_id = send("POST", "/customers", {
                "name": "ZZ_MATRIX_CUSTOMER_6F92", "contact": "ZZ_MATRIX_CONTACT_6F92",
                "area": "ZZ_MATRIX_AREA_6F92",
            }).json()["id"]
            send("PATCH", f"/customers/{customer_id}", {"area": "ZZ_MATRIX_AREA_UPDATED_6F92"})

            # Crop mapping/cycle and input application flows.
            send("PATCH", "/crop-types/1/product-mapping", {"product_id": 1})
            cycle_id = send("POST", "/crop-cycles", {
                "table_id": 1, "batch_id": 1, "crop_type_id": 1, "nursery_start": "2026-02-01",
            }).json()["id"]
            send("PATCH", f"/crop-cycles/{cycle_id}", {"harvest_quantity_kg": 2})
            application_id = send("POST", "/activities", {
                "kind": "fertilize", "cycle_ids": [1], "note": "ZZ_MATRIX_INPUT_NOTE_6F92",
                "items": [{"item_name": "ZZ_MATRIX_INPUT_6F92", "quantity": 1, "unit": "kg"}],
            }).json()["id"]
            send("PATCH", f"/activities/{application_id}", {"note": "ZZ_MATRIX_INPUT_UPDATED_6F92", "reason": "ZZ_MATRIX_REASON_6F92"})

            # Finance, tasks, documents, and insight status.
            entry_id = send("POST", "/finance/entries", {
                "entry_date": "2026-11-01", "direction": "expense", "category": "other",
                "amount": "98765.43", "description": "ZZ_MATRIX_FINANCE_6F92",
            }).json()["id"]
            send("PATCH", f"/finance/entries/{entry_id}", {"description": "ZZ_MATRIX_FINANCE_UPDATED_6F92"})
            send("POST", f"/finance/entries/{entry_id}/void", {"reason": "ZZ_MATRIX_VOID_FINANCE_6F92"})
            task_id = send("POST", "/tasks", {
                "title": "ZZ_MATRIX_TASK_6F92", "due_date": date.today().isoformat(),
                "labor_cost": "345.67", "worker_count": 2, "extra_cost": "456.78",
            }).json()["id"]
            send("PATCH", f"/tasks/{task_id}", {"title": "ZZ_MATRIX_TASK_UPDATED_6F92"})
            inbound_id = send("POST", "/trade/inbound", {
                "supplier_id": 1, "note": "ZZ_MATRIX_INBOUND_6F92",
                "lines": [{"product_id": 1, "quantity": 1, "unit": "kg", "unit_price": "123.45"}],
            }).json()["id"]
            outbound_id = send("POST", "/trade/outbound", {
                "customer_id": 1, "note": "ZZ_MATRIX_OUTBOUND_6F92",
                "lines": [{"product_id": 1, "quantity": 1, "unit": "kg", "unit_price": "234.56"}],
            }).json()["id"]
            send("PATCH", f"/trade/documents/{inbound_id}", {"note": "ZZ_MATRIX_DOCUMENT_UPDATED_6F92"})
            send("POST", f"/trade/documents/{inbound_id}/void", {"reason": "ZZ_MATRIX_VOID_DOCUMENT_6F92"})
            send("POST", f"/trade/documents/{outbound_id}/void", {"reason": "ZZ_MATRIX_VOID_DOCUMENT_6F92"})
            send("PATCH", "/insights/1/status", {"status": "seen"})

            # Soft deletes are last because later flows still reference the records.
            send("DELETE", f"/activities/{application_id}")
            send("DELETE", f"/tasks/{task_id}")
            send("DELETE", f"/crop-cycles/{cycle_id}")
            send("DELETE", f"/products/{product_id}")
            send("DELETE", f"/suppliers/{supplier_id}")
            send("DELETE", f"/customers/{customer_id}")
        finally:
            app.dependency_overrides.clear()
            engine.dispose()


def test_phase2_encrypted_markers_are_absent_from_raw_database(caplog):
    engine, Session = _make_phase2_db()
    try:
        with engine.connect() as connection:
            tables = connection.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).scalars().all()
            raw_values = []
            for table in tables:
                quoted = '"' + table.replace('"', '""') + '"'
                columns = connection.exec_driver_sql(f"PRAGMA table_info({quoted})").all()
                for row in connection.exec_driver_sql(f"SELECT * FROM {quoted}").all():
                    raw_values.extend(str(value) for value in row if value is not None)
            database_text = "\n".join(raw_values)
        assert not any(marker in database_text for marker in MARKERS)
        # Encrypted values are stored as Fernet tokens rather than plaintext markers.
        with Session() as db:
            assert db.scalar(select(Product.name_encrypted)).decode("ascii").startswith("gAAAA")
            assert db.scalar(select(FinanceEntry.amount_encrypted)).decode("ascii").startswith("gAAAA")
        assert not any(marker in "\n".join(record.getMessage() for record in caplog.records) for marker in MARKERS)
    finally:
        engine.dispose()


def test_phase2_create_update_void_and_report_flows_do_not_log_plaintext(caplog):
    engine, Session = _make_phase2_db()
    try:
        client = _client(Session, Role.owner)
        caplog.set_level(logging.DEBUG)
        product = client.post("/products", json={
            "category": "other", "name": "ZZ_WRITE_PRODUCT_6F92", "unit": "kg",
        })
        assert product.status_code == 201, product.text
        product_id = product.json()["id"]
        product_update = client.patch(f"/products/{product_id}", json={"name": "ZZ_WRITE_PRODUCT_UPDATED_6F92"})
        assert product_update.status_code == 200, product_update.text
        supplier = client.post("/suppliers", json={
            "name": "ZZ_WRITE_SUPPLIER_6F92", "contact": "ZZ_WRITE_CONTACT_6F92",
            "area": "ZZ_WRITE_AREA_6F92", "note": "ZZ_WRITE_NOTE_6F92",
        })
        assert supplier.status_code == 201, supplier.text
        supplier_update = client.patch(f"/suppliers/{supplier.json()['id']}", json={"note": "ZZ_WRITE_NOTE_UPDATED_6F92"})
        assert supplier_update.status_code == 200, supplier_update.text
        customer = client.post("/customers", json={
            "name": "ZZ_WRITE_CUSTOMER_6F92", "contact": "ZZ_WRITE_CUSTOMER_CONTACT_6F92",
            "area": "ZZ_WRITE_CUSTOMER_AREA_6F92",
        })
        assert customer.status_code == 201, customer.text
        finance = client.post("/finance/entries", json={
            "direction": "expense", "category": "other", "amount": "98765.43",
            "description": "ZZ_WRITE_FINANCE_6F92",
        })
        assert finance.status_code == 201, finance.text
        finance_update = client.patch(f"/finance/entries/{finance.json()['id']}", json={"description": "ZZ_WRITE_FINANCE_UPDATED_6F92"})
        assert finance_update.status_code == 200, finance_update.text
        task = client.post("/tasks", json={
            "title": "ZZ_WRITE_TASK_6F92", "due_date": date.today().isoformat(),
            "status": "done", "labor_cost": "12345.67", "worker_count": 2,
            "extra_cost": "54321.09",
        })
        assert task.status_code == 201, task.text
        application = client.post("/activities", json={
            "kind": "fertilize", "cycle_ids": [1], "note": "ZZ_WRITE_INPUT_NOTE_6F92",
            "items": [{"item_name": "ZZ_WRITE_INPUT_6F92", "quantity": 1.25, "unit": "kg"}],
        })
        assert application.status_code == 201, application.text
        document = client.post("/trade/inbound", json={
            "supplier_id": supplier.json()["id"], "note": "ZZ_WRITE_DOCUMENT_6F92",
            "lines": [{"product_id": product_id, "quantity": 1, "unit": "kg", "unit_price": "55.55"}],
        })
        assert document.status_code == 201, document.text
        voided = client.post(f"/trade/documents/{document.json()['id']}/void", json={
            "reason": "ZZ_WRITE_VOID_REASON_6F92",
        })
        assert voided.status_code == 200, voided.text
        report = client.get(f"/finance/summary?from={date.today().replace(day=1)}&to={date.today()}")
        assert report.status_code == 200, report.text

        markers = set(MARKERS) | {
            "ZZ_WRITE_PRODUCT_6F92", "ZZ_WRITE_SUPPLIER_6F92", "ZZ_WRITE_CONTACT_6F92",
            "ZZ_WRITE_AREA_6F92", "ZZ_WRITE_NOTE_6F92", "ZZ_WRITE_CUSTOMER_6F92",
            "ZZ_WRITE_CUSTOMER_CONTACT_6F92", "ZZ_WRITE_CUSTOMER_AREA_6F92",
            "ZZ_WRITE_FINANCE_6F92", "ZZ_WRITE_TASK_6F92", "ZZ_WRITE_INPUT_NOTE_6F92",
            "ZZ_WRITE_INPUT_6F92", "ZZ_WRITE_DOCUMENT_6F92", "ZZ_WRITE_VOID_REASON_6F92",
            "ZZ_WRITE_PRODUCT_UPDATED_6F92", "ZZ_WRITE_NOTE_UPDATED_6F92",
            "ZZ_WRITE_FINANCE_UPDATED_6F92",
        }
        all_logs = "\n".join(record.getMessage() for record in caplog.records)
        assert not any(marker in all_logs for marker in markers), all_logs
        with engine.connect() as connection:
            tables = connection.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).scalars().all()
            raw = []
            for table_name in tables:
                quoted = '"' + table_name.replace('"', '""') + '"'
                raw.extend(
                    str(value)
                    for row in connection.exec_driver_sql(f"SELECT * FROM {quoted}").all()
                    for value in row
                    if value is not None
                )
        database_text = "\n".join(raw)
        assert not any(marker in database_text for marker in markers), database_text
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
