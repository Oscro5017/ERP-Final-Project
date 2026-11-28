from datetime import UTC, date, datetime
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import Batch, CropCycle, CropType, FinanceEntry, Role, Table, Activity, User
from app.security import get_current_user
from app.services.products_stock import record_movement
from app.services.secure_fields import encrypt_number


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
        ])
        db.commit()
    return Session


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


def test_dashboard_summary_uses_product_cycle_task_and_finance_data(monkeypatch):
    Session = make_db()
    import app.routers.dashboard as dashboard_router

    monkeypatch.setattr(dashboard_router, "_today_bangkok", lambda: date(2025, 3, 15))
    with API(Session) as client:
        response = client.post("/products", json={"category": "vegetable", "name": "Green Oak", "unit": "kg"})
        product_id = response.json()["id"]
        with Session() as db:
            record_movement(db, product_id, -2, "kg", "shipment", occurred_at=datetime(2025, 3, 1, tzinfo=UTC))
            db.add_all([
                CropCycle(table_id=1, batch_id=1, crop_type_id=1, nursery_start=date(2025, 3, 1), status="nursery", cycle_code="250301"),
                CropCycle(table_id=1, batch_id=1, crop_type_id=1, nursery_start=date(2025, 3, 2), status="ready_to_harvest", cycle_code="250302"),
                Activity(title="due", planned_date=date(2025, 3, 15), status="pending"),
                Activity(title="late", planned_date=date(2025, 3, 14), status="pending"),
                Activity(title="done", planned_date=date(2025, 3, 10), status="done"),
                FinanceEntry(entry_date=date(2025, 3, 1), direction="income", category="sale", amount_encrypted=encrypt_number(100).encode("ascii"), is_auto=False, status="posted"),
                FinanceEntry(entry_date=date(2025, 3, 2), direction="expense", category="other", amount_encrypted=encrypt_number(30).encode("ascii"), is_auto=False, status="posted"),
                FinanceEntry(entry_date=date(2025, 2, 28), direction="income", category="sale", amount_encrypted=encrypt_number(999).encode("ascii"), is_auto=False, status="posted"),
            ])
            db.commit()
        body = client.get("/dashboard/summary").json()
        assert body["as_of"] == "2025-03-15"
        assert body["product_count"] == 1 and body["negative_product_count"] == 1
        assert body["crop_cycles_by_status"]["nursery"] == 1
        assert body["crop_cycles_by_status"]["ready_to_harvest"] == 1
        assert body["tasks_due_today"] == 1 and body["tasks_overdue"] == 1
        assert body["finance_month"]["income"]["value"] == 100
        assert body["finance_month"]["expense"]["value"] == 30
        assert body["finance_month"]["profit"]["value"] == 70


def test_dashboard_masks_monthly_finance_for_developer(monkeypatch):
    Session = make_db()
    import app.routers.dashboard as dashboard_router

    monkeypatch.setattr(dashboard_router, "_today_bangkok", lambda: date(2025, 3, 15))
    with Session() as db:
        db.add(FinanceEntry(entry_date=date(2025, 3, 1), direction="income", category="sale", amount_encrypted=encrypt_number(20).encode("ascii"), is_auto=False, status="posted"))
        db.commit()
    with API(Session, Role.developer) as client:
        body = client.get("/dashboard/summary").json()
        assert body["finance_month"]["income"]["is_masked"] is True
        assert body["finance_month"]["income"]["value"] != "20"


def test_dashboard_skips_bad_finance_ciphertext_and_auth_is_required(monkeypatch):
    Session = make_db()
    import app.routers.dashboard as dashboard_router

    monkeypatch.setattr(dashboard_router, "_today_bangkok", lambda: date(2025, 3, 15))
    with Session() as db:
        db.add(FinanceEntry(entry_date=date(2025, 3, 1), direction="income", category="sale", amount_encrypted=b"broken", is_auto=False, status="posted"))
        db.commit()
    with API(Session) as client:
        assert client.get("/dashboard/summary").json()["finance_month"]["skipped_decrypt_failed"] == 1
        app.dependency_overrides.pop(get_current_user, None)
        assert client.get("/dashboard/summary").status_code == 401
