from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import Batch, CropType, Role, Table, User
from app.security import get_current_user
from app.services.freshness import today_bangkok

TODAY = today_bangkok()


def day(offset):
    return str(TODAY + timedelta(days=offset))


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
                Table(id=1, table_number=1),
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
        self.product = self.call("POST", "/products", {"category": "vegetable", "name": "ผักลับ", "unit": "kg"}, 201)["id"]
        self.shelf(5, 1)

    def call(self, method, path, body=None, status=200):
        response = self.client.request(method, path, json=body)
        assert response.status_code == status, response.text
        return response.json() if response.content else None

    def shelf(self, days, warn, status=200):
        return self.call("PUT", f"/freshness/products/{self.product}",
                         {"shelf_life_days": days, "warn_days": warn}, status)

    def trade(self, kind, quantity, offset):
        return self.call("POST", f"/trade/{kind}", {
            "doc_date": day(offset), "lines": [{"product_id": self.product, "quantity": quantity}],
        }, 201)

    def lots(self, empty=True):
        return self.call("GET", f"/freshness/lots?include_empty={str(empty).lower()}")

    def remaining(self):
        return [lot["remaining_quantity"] for lot in self.lots()["items"] if lot["status"] != "empty"]

    def waste(self, lot, quantity, status=201, **extra):
        return self.call("POST", "/freshness/waste", {
            "product_id": self.product, "lot_key": lot["lot_key"], "quantity": quantity, "reason": "spoiled", **extra,
        }, status)

    def balance(self):
        return self.call("GET", f"/stock/balances?product_id={self.product}")["items"][0]["quantity"]


@pytest.fixture
def env():
    environment = Env()
    yield environment
    app.dependency_overrides.clear()


def test_lots_have_expiry_and_status(env):
    for offset in (-6, -4, 0):
        env.trade("inbound", 10, offset)
    data = env.lots()
    assert [lot["status"] for lot in data["items"]] == ["expired", "expiring", "fresh"]
    assert [lot["expires_on"] for lot in data["items"]] == [day(-1), day(1), day(5)]
    assert (data["expired"], data["expiring"]) == (1, 1)


def test_lot_is_usable_on_its_expiry_date(env):
    env.trade("inbound", 10, -5)
    assert env.lots()["items"][0]["status"] == "expiring"
    assert env.trade("outbound", 1, 0)["warnings"] == []


def test_ships_first_expiring_good_lot_and_leaves_expired(env):
    env.trade("inbound", 10, -6)  # expired
    env.trade("inbound", 10, -1)
    env.trade("inbound", 10, -3)
    document = env.trade("outbound", 12, 0)
    assert document["warnings"] == []
    assert [(lot["received_on"], lot["remaining_quantity"]) for lot in env.lots()["items"] if lot["status"] != "empty"] == [
        (day(-6), 10.0), (day(-1), 8.0)]


def test_using_expired_lot_warns_but_does_not_block(env):
    env.trade("inbound", 10, -6)
    document = env.trade("outbound", 4, 0)
    assert document["warnings"] == [f"expired_lot:{env.product}"]
    assert env.call("GET", f"/trade/documents/{document['id']}")["warnings"] == document["warnings"]
    assert env.remaining() == [6.0]


def test_backdated_sale_before_expiry_is_not_a_warning(env):
    env.trade("inbound", 10, -6)
    assert env.trade("outbound", 4, -3)["warnings"] == []


def test_waste_hits_chosen_lot_and_stock_and_can_be_voided(env):
    env.trade("inbound", 10, -3)
    env.trade("inbound", 10, 0)
    later = env.lots()["items"][1]
    waste = env.waste(later, 4)
    assert waste["created_at"].endswith(("Z", "+00:00"))
    assert env.remaining() == [10.0, 6.0] and env.balance() == 16
    assert env.lots()["items"][1]["wasted_quantity"] == 4
    env.call("POST", f"/freshness/waste/{waste['id']}/void")
    assert env.remaining() == [10.0, 10.0] and env.balance() == 20
    env.call("POST", f"/freshness/waste/{waste['id']}/void", status=409)


def test_waste_cannot_exceed_lot_or_use_unknown_lot(env):
    env.trade("inbound", 10, 0)
    lot = env.lots()["items"][0]
    env.waste(lot, 10.5, 409)
    env.waste(lot, 0, 422)
    env.waste({"lot_key": "movement-999"}, 1, 422)
    assert env.balance() == 10 and env.call("GET", "/freshness/waste")["total"] == 0


def test_voiding_shipment_returns_quantity_to_lot(env):
    env.trade("inbound", 10, 0)
    document = env.trade("outbound", 7, 0)
    assert env.remaining() == [3.0]
    env.call("POST", f"/trade/documents/{document['id']}/void", {"reason": "ผิด"})
    assert env.remaining() == [10.0]


def test_harvest_lot_uses_harvest_date_and_survives_quantity_edit(env):
    env.call("PATCH", "/crop-types/1/product-mapping", {"product_id": env.product})
    cycle = env.call("POST", "/crop-cycles", {
        "table_id": 1, "batch_id": 1, "crop_type_id": 1, "nursery_start": "2025-01-01",
        "status": "harvested", "harvest_date": day(-3), "harvest_quantity_kg": 20,
    }, 201)
    lot = env.lots()["items"][0]
    assert (lot["cycle_id"], lot["received_on"], lot["expires_on"]) == (cycle["id"], day(-3), day(2))
    env.waste(lot, 5)
    env.call("PATCH", f"/crop-cycles/{cycle['id']}", {"harvest_quantity_kg": 30})
    edited = env.lots()["items"][0]
    assert (edited["lot_key"], edited["remaining_quantity"], edited["wasted_quantity"]) == (lot["lot_key"], 25.0, 5.0)


def test_expiry_override_needs_reason_and_valid_date(env):
    env.trade("inbound", 10, -6)
    lot = env.lots()["items"][0]
    path = f"/freshness/products/{env.product}/lots/{lot['lot_key']}/expiry"
    env.call("PUT", path, {"expires_on": day(3), "reason": "  "}, 422)
    env.call("PUT", path, {"expires_on": day(-7), "reason": "x"}, 422)
    item = env.call("PUT", path, {"expires_on": day(3), "reason": "แช่เย็น"})["items"][0]
    assert (item["expires_on"], item["status"], item["expiry_overridden"]) == (day(3), "fresh", True)


def test_oversold_quantity_is_reported_and_settled_by_next_lot(env):
    env.trade("outbound", 4, -1)
    assert env.lots()["products"][0]["uncovered_quantity"] == 4
    env.trade("inbound", 10, 0)
    assert env.remaining() == [6.0] and env.lots()["products"][0]["uncovered_quantity"] == 0


def test_lot_total_always_matches_ledger(env):
    env.trade("inbound", 10.5, -6)
    env.trade("inbound", 3.333, -2)
    env.trade("outbound", 5.111, -1)
    env.waste(env.lots()["items"][0], 1.2)
    env.call("POST", f"/products/{env.product}/adjustments", {"counted_quantity": 6})
    assert round(sum(env.remaining()), 3) == env.balance() == 6


def test_setting_validation_and_removal(env):
    env.shelf(2, 3, 422)
    env.call("PUT", "/freshness/products/999", {"shelf_life_days": 1, "warn_days": 0}, 422)
    env.trade("inbound", 10, -6)
    env.call("DELETE", f"/freshness/products/{env.product}", status=204)
    assert env.lots()["items"] == []
    assert env.trade("outbound", 1, 0)["warnings"] == []
    env.call("DELETE", f"/freshness/products/{env.product}", status=404)


def test_notes_are_encrypted_and_masked(env):
    env.trade("inbound", 10, 0)
    lot = env.lots()["items"][0]
    env.waste(lot, 1, note="โน้ตลับ")
    env.call("PUT", f"/freshness/products/{env.product}/lots/{lot['lot_key']}/expiry",
             {"expires_on": day(9), "reason": "เหตุผลลับ"})
    with env.engine.connect() as connection:
        raw = str([connection.execute(text(f"SELECT * FROM {table}")).all()
                   for table in ("stock_waste", "lot_expiry_overrides")])
    assert "ลับ" not in raw
    env.role = Role.developer
    for path in ("/freshness/waste", "/freshness/lots"):
        assert "ลับ" not in env.client.get(path).text


def test_requires_login():
    app.dependency_overrides.clear()
    assert TestClient(app).get("/freshness/lots").status_code in (401, 403)
