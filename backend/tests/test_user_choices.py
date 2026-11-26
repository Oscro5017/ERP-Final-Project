from decimal import Decimal

import pytest

from app.main import app
from app.models import FinanceEntry, Role, SalesOrderLinePrice, StockDocumentPurpose, User
from app.security import get_current_user
from app.services.sales_orders import replan_open_orders_job
from tests.test_order_supply import Linked, day


class Choices(Linked):
    def priced_order(self, quantity=10, price="50", **extra):
        return self.post("/sales-orders", {"customer_id": self.customer, "lines": [{
            "product_id": self.product, "quantity": quantity, "delivery_date": day(60), "unit_price": price,
        }], **extra})

    def outbound(self, price="20", status=201, **extra):
        return self.post("/trade/outbound", {
            "lines": [{"product_id": self.product, "quantity": 2, "unit_price": price}], **extra}, status)

    def finance(self):
        with self.Session() as db:
            rows = db.query(FinanceEntry).filter(FinanceEntry.status == "posted").all()
            return [(row.direction, row.category) for row in rows]

    def deliver_body(self, order, quantity=10, body=None, **line):
        return self.post(f"/sales-orders/{order['id']}/deliver", {
            "lines": [{"line_id": order["lines"][0]["id"], "quantity": quantity, **line}], **(body or {})})


@pytest.fixture
def env():
    environment = Choices()
    yield environment
    app.dependency_overrides.clear()


def test_sale_document_records_income_by_default(env):
    document = env.outbound(purpose="sale")
    assert document["purpose"] == "sale" and document["finance_recorded"]
    assert env.finance() == [("income", "sale")]
    assert env.balance() == -2


def test_document_without_purpose_keeps_previous_behaviour(env):
    document = env.outbound()
    assert document["purpose"] is None and document["finance_recorded"]


def test_other_document_skips_income_unless_chosen(env):
    assert not env.outbound(purpose="other")["finance_recorded"]
    assert env.finance() == []
    assert env.outbound(purpose="other", record_finance=True)["finance_recorded"]
    assert env.finance() == [("income", "other")]


def test_manual_finance_can_be_recorded_later_only_once(env):
    document = env.outbound(purpose="sale", record_finance=False)
    assert env.finance() == []
    assert env.post(f"/trade/documents/{document['id']}/finance", {}, 200)["finance_recorded"]
    env.post(f"/trade/documents/{document['id']}/finance", {}, 409)
    assert env.finance() == [("income", "sale")]


def test_finance_rejects_void_and_unpriced_documents(env):
    unpriced = env.outbound(price=None)
    env.post(f"/trade/documents/{unpriced['id']}/finance", {}, 422)
    env.post(f"/trade/documents/{unpriced['id']}/void", {}, 200)
    env.post(f"/trade/documents/{unpriced['id']}/finance", {}, 409)
    env.post("/trade/documents/999/finance", {}, 404)


def test_inbound_finance_choice(env):
    body = {"lines": [{"product_id": env.product, "quantity": 1, "unit_price": 5}]}
    assert not env.post("/trade/inbound", {**body, "record_finance": False})["finance_recorded"]
    assert env.post("/trade/inbound", body)["finance_recorded"]


@pytest.mark.parametrize("purpose", ["sale", "other", None])
def test_void_returns_stock_and_income(env, purpose):
    document = env.outbound(purpose=purpose, record_finance=True)
    voided = env.post(f"/trade/documents/{document['id']}/void", {}, 200)
    assert not voided["finance_recorded"]
    assert env.balance() == 0 and env.finance() == []


def test_order_price_is_used_for_delivery(env):
    order = env.priced_order()
    line = order["lines"][0]
    assert Decimal(line["unit_price"]) == 50 and line["has_price"]
    result = env.deliver_body(order, use_order_price=True)
    document = env.get(f"/trade/documents/{result['document_id']}")
    assert Decimal(document["total_amount"]["value"]) == 500
    assert document["purpose"] == "order" and document["order_no"] == order["order_no"]
    assert result["order"]["status"] == "delivered"


def test_typed_price_wins_over_order_price(env):
    result = env.deliver_body(env.priced_order(), use_order_price=True, unit_price="7")
    document = env.get(f"/trade/documents/{result['document_id']}")
    assert Decimal(document["total_amount"]["value"]) == 70


def test_delivery_without_price_choice_stays_unpriced(env):
    result = env.deliver_body(env.priced_order())
    assert env.get(f"/trade/documents/{result['document_id']}")["total_amount"] is None


def test_delivery_choices_skip_finance_and_closing(env):
    order = env.priced_order()
    result = env.deliver_body(
        order, use_order_price=True, body={"record_finance": False, "close_when_complete": False, "note": "x"})
    assert result["order"]["status"] == "open"
    assert result["order"]["lines"][0]["planting_status"] == "delivered"
    assert env.finance() == []
    assert env.post(f"/sales-orders/{order['id']}/close", {"status": "delivered"}, 200)["status"] == "delivered"


def test_void_order_delivery_reopens_order(env):
    result = env.deliver_body(env.priced_order(), use_order_price=True)
    env.post(f"/trade/documents/{result['document_id']}/void", {}, 200)
    assert env.get(f"/sales-orders/{result['order']['id']}")["status"] == "open"
    assert env.finance() == []


def test_developer_never_sees_prices_and_does_not_erase_them(env):
    order = env.priced_order()
    env.outbound(purpose="sale")
    env.role = Role.developer
    line = env.get(f"/sales-orders/{order['id']}")["lines"][0]
    assert line["has_price"] and "50" != line["unit_price"] and len(line["unit_price"]) > 50
    assert env.get("/trade/last-prices") == []
    env.patch(f"/sales-orders/{order['id']}", {"lines": [{
        "id": line["id"], "product_id": env.product, "quantity": 12, "delivery_date": day(60)}]})
    result = env.deliver_body(order, quantity=12, use_order_price=True)
    env.role = Role.owner
    document = env.get(f"/trade/documents/{result['document_id']}")
    assert Decimal(document["total_amount"]["value"]) == 600


def test_price_is_removed_explicitly_or_with_its_line(env):
    order = env.priced_order()
    base = {"product_id": env.product, "quantity": 10, "delivery_date": day(60)}
    changed = env.patch(f"/sales-orders/{order['id']}", {"lines": [
        {**base, "id": order["lines"][0]["id"], "unit_price": None}]})
    assert not changed["lines"][0]["has_price"]
    env.patch(f"/sales-orders/{order['id']}", {"lines": [{**base, "unit_price": "9"}]})
    env.patch(f"/sales-orders/{order['id']}", {"lines": [base]})
    with env.Session() as db:
        assert db.query(SalesOrderLinePrice).count() == 0


def test_last_prices_use_newest_posted_sale(env):
    env.outbound(price="20", purpose="sale", doc_date=day(-2))
    env.outbound(price="30", purpose="sale", doc_date=day(-1))
    newest = env.outbound(price="40", purpose="sale")
    env.outbound(price="99", purpose="other")
    assert [Decimal(item["unit_price"]) for item in env.get("/trade/last-prices")] == [40]
    env.post(f"/trade/documents/{newest['id']}/void", {}, 200)
    assert [Decimal(item["unit_price"]) for item in env.get("/trade/last-prices")] == [30]
    assert env.get("/trade/last-prices?doc_type=inbound") == []


def test_sales_list_contains_sales_and_orders_only(env):
    sale = env.outbound(purpose="sale")["id"]
    old = env.outbound()["id"]
    env.outbound(purpose="other")
    env.receive(5)
    delivered = env.deliver_body(env.priced_order())["document_id"]
    listed = {item["id"] for item in env.get("/trade/documents?sales_only=true")["items"]}
    assert listed == {sale, old, delivered}


def test_old_delivery_document_is_recognised_as_order(env):
    result = env.deliver_body(env.priced_order())
    with env.Session() as db:
        db.query(StockDocumentPurpose).delete()
        db.commit()
    document = env.get(f"/trade/documents/{result['document_id']}")
    assert document["purpose"] == "order" and document["order_no"] == result["order"]["order_no"]


def test_manual_order_never_creates_planting_task(env):
    order = env.priced_order(auto_planting=False)
    line = order["lines"][0]
    assert not order["auto_planting"]
    assert line["planting_status"] == "manual" and line["latest_sow_date"] and line["planting_ready"]
    with env.Session() as db:
        replan_open_orders_job(db)
    env.receive(1)
    assert env.pending() == []


def test_order_planting_choice_can_be_switched(env):
    order = env.priced_order()
    assert len(env.pending()) == 1
    env.patch(f"/sales-orders/{order['id']}", {"auto_planting": False})
    assert env.pending() == []
    env.patch(f"/sales-orders/{order['id']}", {"auto_planting": True})
    assert len(env.pending()) == 1


def test_manual_order_can_still_create_cycles(env):
    order = env.priced_order(auto_planting=False)
    line = order["lines"][0]["id"]
    assert env.get(f"/sales-orders/lines/{line}/planting")["can_create"]
    env.post(f"/sales-orders/lines/{line}/planting", {
        "table_ids": [1], "nursery_start": day(0), "create_tasks": False})
    assert env.line(order)["planting_status"] == "planted"
    assert env.get("/tasks") == []


def test_cycle_tasks_choice_covers_later_stages(env):
    cycle = env.cycle(0, create_tasks=False)
    env.patch(f"/crop-cycles/{cycle['id']}", {"status": "bushed", "transplant_date": day(0)})
    assert env.get("/tasks") == []
    env.cycle(0, table=2)
    assert len(env.get("/tasks")) == 1


def test_harvest_stock_choice_is_remembered_and_reversible(env):
    cycle = env.cycle(-50)
    path = f"/crop-cycles/{cycle['id']}"
    env.patch(path, {"status": "harvested", "harvest_quantity_kg": 8, "record_harvest_stock": False})
    assert env.balance() == 0
    env.patch(path, {"harvest_quantity_kg": 9})
    assert env.balance() == 0
    env.patch(path, {"record_harvest_stock": True})
    assert env.balance() == 9


def test_movement_has_readable_source(env):
    document = env.receive(3)
    env.patch(f"/crop-cycles/{env.cycle(-50)['id']}", {"status": "harvested", "harvest_quantity_kg": 8})
    movements = env.get("/stock/movements")["items"]
    assert all(item["occurred_at"].endswith("Z") for item in movements)
    labels = {item["source_label"] for item in env.get("/stock/movements")["items"]}
    assert document["doc_no"] in labels
    assert any(label.startswith("โต๊ะ 1") for label in labels)


def test_preferences_belong_to_one_user(env):
    path = "/preferences/automation"
    assert env.client.put(f"{path}/order_fill", json={"mode": "auto"}).status_code == 204
    assert env.client.put(f"{path}/order_fill", json={"mode": "manual"}).status_code == 204
    assert env.get(path) == {"order_fill": "manual"}
    with env.Session() as db:
        db.add(User(id=2, username="second", password_hash="unused", role=Role.developer))
        db.commit()
    previous = app.dependency_overrides[get_current_user]
    app.dependency_overrides[get_current_user] = lambda: User(id=2, username="second", role=Role.developer)
    assert env.get(path) == {}
    app.dependency_overrides[get_current_user] = previous
    assert env.client.delete(f"{path}/order_fill").status_code == 204
    assert env.get(path) == {}


def test_preferences_reject_unknown_values(env):
    assert env.client.put("/preferences/automation/nope", json={"mode": "auto"}).status_code == 422
    assert env.client.put("/preferences/automation/order_fill", json={"mode": "maybe"}).status_code == 422


def test_outbound_rejects_order_purpose_without_an_order(env):
    env.outbound(purpose="order", status=422)
