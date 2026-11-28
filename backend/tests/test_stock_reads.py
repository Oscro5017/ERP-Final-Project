from datetime import UTC, date, datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import Role, StockMovement, Activity, User
from app.security import get_current_user
from app.services.products_stock import record_movement


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


def add_product(client, name, reorder_point=None):
    payload = {"category": "vegetable", "name": name, "unit": "kg"}
    if reorder_point is not None:
        payload["reorder_point"] = reorder_point
    response = client.post("/products", json=payload)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def movement(db, product_id, quantity, movement_type, occurred_at, note=None):
    entry = record_movement(db, product_id, quantity, "kg", movement_type, occurred_at=occurred_at, note=note)
    return entry


def test_balances_sum_active_movements_as_of_bangkok_end_of_day():
    Session = make_db()
    with API(Session) as client:
        product_id = add_product(client, "Balance Product")
        with Session() as db:
            movement(db, product_id, 10, "receipt", datetime(2025, 3, 1, 16, 59, tzinfo=UTC))
            movement(db, product_id, -3, "shipment", datetime(2025, 3, 1, 16, 0, tzinfo=UTC))
            voided = movement(db, product_id, 7, "receipt", datetime(2025, 3, 1, 12, 0, tzinfo=UTC))
            voided.voided_at = datetime(2025, 3, 2, tzinfo=UTC)
            movement(db, product_id, 100, "receipt", datetime(2025, 3, 2, 1, 0, tzinfo=UTC))
            db.commit()
        response = client.get(f"/stock/balances?product_id={product_id}&as_of=2025-03-01")
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1 and len(body["items"]) == 1
        assert body["items"][0]["quantity"] == 7 and body["items"][0]["negative"] is False
        assert body["items"][0]["as_of"] == "2025-03-01"


def test_balances_mark_negative_and_return_all_products_with_pagination():
    Session = make_db()
    with API(Session) as client:
        p1 = add_product(client, "Product One")
        p2 = add_product(client, "Product Two")
        with Session() as db:
            movement(db, p1, -2, "shipment", datetime(2025, 3, 1, tzinfo=UTC))
            db.commit()
        response = client.get("/stock/balances?as_of=2025-03-02&limit=1")
        assert response.status_code == 200 and response.json()["total"] == 2
        assert len(response.json()["items"]) == 1
        negative = client.get(f"/stock/balances?product_id={p1}&as_of=2025-03-02").json()["items"][0]
        zero = client.get(f"/stock/balances?product_id={p2}&as_of=2025-03-02").json()["items"][0]
        assert negative["negative"] and negative["quantity"] == -2
        assert zero["negative"] is False and zero["quantity"] == 0


def test_balances_mask_product_name_for_developer_and_404_missing_product():
    Session = make_db()
    with API(Session) as client:
        product_id = add_product(client, "SECRET_PRODUCT_NAME")
    with API(Session, Role.developer) as client:
        body = client.get(f"/stock/balances?product_id={product_id}").json()["items"][0]
        assert body["is_masked"] is True and body["product_name"] != "SECRET_PRODUCT_NAME"
        assert client.get("/stock/balances?product_id=9999").status_code == 404


def test_movement_filters_by_product_type_source_date_and_hides_void_by_default():
    Session = make_db()
    with API(Session) as client:
        product_id = add_product(client, "Movement Product")
        with Session() as db:
            first = movement(db, product_id, 5, "receipt", datetime(2025, 3, 1, 12, tzinfo=UTC), "FIRST_NOTE")
            second = movement(db, product_id, -2, "shipment", datetime(2025, 3, 2, 12, tzinfo=UTC))
            second.source_type = "stock_document"
            second.source_id = 71
            first.voided_at = datetime(2025, 3, 3, tzinfo=UTC)
            db.commit()
        hidden = client.get("/stock/movements?product_id={}&from=2025-03-01&to=2025-03-01".format(product_id))
        assert hidden.status_code == 200 and hidden.json()["total"] == 0
        visible = client.get(f"/stock/movements?product_id={product_id}&movement_type=shipment&source_type=stock_document&source_id=71")
        assert visible.json()["total"] == 1 and visible.json()["items"][0]["quantity_delta"] == -2
        with_void = client.get(f"/stock/movements?product_id={product_id}&include_void=true")
        assert with_void.json()["total"] == 2


def test_movement_date_filters_use_bangkok_calendar_day():
    Session = make_db()
    with API(Session) as client:
        product_id = add_product(client, "Date Product")
        with Session() as db:
            movement(db, product_id, 1, "receipt", datetime(2025, 3, 1, 16, 59, tzinfo=UTC))
            movement(db, product_id, 2, "receipt", datetime(2025, 3, 1, 17, 0, tzinfo=UTC))
            db.commit()
        response = client.get(f"/stock/movements?product_id={product_id}&from=2025-03-01&to=2025-03-01")
        assert response.json()["total"] == 1 and response.json()["items"][0]["quantity_delta"] == 1


def test_movement_pagination_and_validation():
    Session = make_db()
    with API(Session) as client:
        product_id = add_product(client, "Page Product")
        with Session() as db:
            for index in range(3):
                movement(db, product_id, 1, "receipt", datetime(2025, 3, index + 1, tzinfo=UTC))
            db.commit()
        assert client.get("/stock/movements?movement_type=bad").status_code == 422
        assert client.get("/stock/movements?from=2025-03-03&to=2025-03-01").status_code == 422
        page = client.get("/stock/movements?product_id={}&limit=1&offset=1".format(product_id))
        assert page.status_code == 200 and page.json()["total"] == 3 and len(page.json()["items"]) == 1


def test_movement_note_masks_for_developer_and_owner_can_read():
    Session = make_db()
    with API(Session) as client:
        product_id = add_product(client, "Private Note Product")
        with Session() as db:
            movement(db, product_id, 1, "receipt", datetime(2025, 3, 1, tzinfo=UTC), "PRIVATE_NOTE")
            db.commit()
    with API(Session, Role.developer) as client:
        response = client.get(f"/stock/movements?product_id={product_id}")
        assert response.json()["items"][0]["note"] != "PRIVATE_NOTE"
    with API(Session) as client:
        response = client.get(f"/stock/movements?product_id={product_id}")
        assert response.json()["items"][0]["note"] == "PRIVATE_NOTE"


def test_stock_read_endpoints_require_authentication():
    Session = make_db()
    with API(Session) as client:
        app.dependency_overrides.pop(get_current_user, None)
        assert client.get("/stock/balances").status_code == 401
        assert client.get("/stock/movements").status_code == 401


def test_low_stock_alert_is_created_once_and_closed_when_restocked():
    Session = make_db()
    with API(Session) as client:
        product_id = add_product(client, "Private Low Stock Item", reorder_point=5)
        assert client.post(f"/products/{product_id}/adjustments", json={"counted_quantity": 4, "unit": "kg"}).status_code == 200
        with Session() as db:
            alerts = db.scalars(select(Activity).where(Activity.stock_alert_product_id == product_id)).all()
            assert len(alerts) == 1 and alerts[0].status == "pending" and alerts[0].is_encrypted
            first_alert_id = alerts[0].id
        assert client.post(f"/products/{product_id}/adjustments", json={"counted_quantity": 3, "unit": "kg"}).status_code == 200
        with Session() as db:
            assert len(db.scalars(select(Activity).where(Activity.stock_alert_product_id == product_id, Activity.status == "pending")).all()) == 1
        assert client.post(f"/products/{product_id}/adjustments", json={"counted_quantity": 6, "unit": "kg"}).status_code == 200
        with Session() as db:
            assert db.get(Activity, first_alert_id).status == "done"
        assert client.post(f"/products/{product_id}/adjustments", json={"counted_quantity": 4, "unit": "kg"}).status_code == 200
        with Session() as db:
            alerts = db.scalars(select(Activity).where(Activity.stock_alert_product_id == product_id, Activity.status == "pending")).all()
            assert len(alerts) == 1 and alerts[0].id != first_alert_id
    with API(Session, Role.developer) as client:
        response = client.get("/tasks")
        alert = next(task for task in response.json() if task.get("is_masked"))
        assert "Private Low Stock Item" not in alert["title"]


def test_reorder_point_does_not_create_duplicate_open_alerts_for_repeated_movements():
    Session = make_db()
    with API(Session) as client:
        product_id = add_product(client, "Repeated Low Stock Item", reorder_point=5)
        assert client.post(f"/products/{product_id}/adjustments", json={"counted_quantity": 4, "unit": "kg"}).status_code == 200
        with Session() as db:
            first = db.scalar(select(Activity).where(Activity.stock_alert_product_id == product_id, Activity.status == "pending"))
            first_id = first.id
        assert client.post(f"/products/{product_id}/adjustments", json={"counted_quantity": 3, "unit": "kg"}).status_code == 200
        with Session() as db:
            alerts = db.scalars(select(Activity).where(Activity.stock_alert_product_id == product_id)).all()
            open_alerts = [task for task in alerts if task.status == "pending"]
            assert len(alerts) == 1 and len(open_alerts) == 1 and open_alerts[0].id == first_id


def test_reorder_point_creates_new_alert_after_restock_and_second_crossing():
    Session = make_db()
    with API(Session) as client:
        product_id = add_product(client, "Second Low Stock Crossing", reorder_point=5)
        for quantity in (4, 6, 4):
            response = client.post(
                f"/products/{product_id}/adjustments",
                json={"counted_quantity": quantity, "unit": "kg"},
            )
            assert response.status_code == 200, response.text
        with Session() as db:
            alerts = db.scalars(select(Activity).where(Activity.stock_alert_product_id == product_id).order_by(Activity.id)).all()
            assert len(alerts) == 2
            assert alerts[0].status == "done"
            assert alerts[1].status == "pending"
