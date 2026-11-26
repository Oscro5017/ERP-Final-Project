from datetime import timedelta

import pytest

from app.main import app
from app.models import FinanceEntry
from app.services.order_supply import today_bangkok
from app.services.sales_orders import replan_open_orders_job
from tests.test_sales_orders import Env

TODAY = today_bangkok()


def day(offset):
    return str(TODAY + timedelta(days=offset))


class Linked(Env):
    def shelf(self, days=10):
        response = self.client.put(
            f"/freshness/products/{self.product}", json={"shelf_life_days": days, "warn_days": 1})
        assert response.status_code == 200, response.text

    def receive(self, quantity, offset=0):
        return self.post("/trade/inbound", {
            "doc_date": day(offset), "lines": [{"product_id": self.product, "quantity": quantity}]})

    def cycle(self, start, table=1, **extra):
        return self.post("/crop-cycles", {
            "table_id": table, "batch_id": 1, "crop_type_id": 1, "nursery_start": day(start), **extra})

    def line(self, order):
        return self.get(f"/sales-orders/{order['id']}")["lines"][0]

    def pending(self):
        return [task for task in self.get("/tasks?status=pending") if task["order_line_id"]]

    def deliver(self, order, quantity, status=201, **extra):
        body = {"lines": [{"line_id": order["lines"][0]["id"], "quantity": quantity, **extra}]}
        return self.post(f"/sales-orders/{order['id']}/deliver", body, status)

    def balance(self):
        return self.get(f"/stock/balances?product_id={self.product}")["items"][0]["quantity"]


@pytest.fixture
def env():
    environment = Linked()
    yield environment
    app.dependency_overrides.clear()


def numbers(line):
    return line["from_stock"], line["from_growing"], line["to_plant"]


def test_stock_good_until_delivery_reduces_planting(env):
    env.shelf(10)
    env.receive(10)
    order = env.order(days=5)
    assert numbers(order["lines"][0]) == (10, 0, 15)
    assert "15 kg" in env.pending()[0]["title"]


def test_stock_that_expires_before_delivery_is_not_counted(env):
    env.shelf(10)
    env.receive(30)
    assert numbers(env.order(days=11)["lines"][0]) == (0, 0, 25)
    assert numbers(env.order(days=10)["lines"][0]) == (25, 0, 0)


def test_untracked_stock_is_not_counted(env):
    env.receive(100)
    assert numbers(env.order(days=5)["lines"][0]) == (0, 0, 25)


def test_full_cover_needs_no_activity_and_follows_stock_changes(env):
    env.shelf(10)
    document = env.receive(30)
    order = env.order(days=5)
    assert order["lines"][0]["planting_status"] == "covered" and env.pending() == []
    env.post(f"/trade/documents/{document['id']}/void", {"reason": "ผิด"}, 200)
    assert len(env.pending()) == 1
    env.receive(30)
    assert env.pending() == []


def test_waste_and_shelf_life_changes_trigger_replanning(env):
    env.shelf(10)
    env.receive(25)
    order = env.order(days=5)
    lot = env.get("/freshness/lots")["items"][0]
    env.post("/freshness/waste", {
        "product_id": env.product, "lot_key": lot["lot_key"], "quantity": 5, "reason": "spoiled"})
    assert numbers(env.line(order)) == (20, 0, 5) and "5 kg" in env.pending()[0]["title"]
    env.shelf(3)
    assert numbers(env.line(order)) == (0, 0, 25) and "25 kg" in env.pending()[0]["title"]


def test_earlier_delivery_gets_stock_first_without_double_counting(env):
    env.shelf(20)
    env.receive(30)
    late, early = env.order(days=10), env.order(days=5)
    assert numbers(env.line(early)) == (25, 0, 0)
    assert numbers(env.line(late)) == (5, 0, 20)


def test_growing_cycle_counts_only_when_ready_in_time(env):
    env.shelf(10)
    env.cycle(-100, status="harvested", harvest_quantity_kg=20, harvest_date=day(-50))
    env.cycle(-32, table=2)  # ready in 10 days
    assert numbers(env.order(days=9)["lines"][0]) == (0, 0, 25)
    order = env.order(days=10)
    assert numbers(order["lines"][0]) == (0, 20, 5)
    moved = env.patch(f"/sales-orders/{order['id']}", {"safety_days": 1})
    assert numbers(moved["lines"][0]) == (0, 0, 25)


def test_growing_without_yield_history_is_not_guessed(env):
    env.shelf(10)
    env.cycle(-32)
    assert numbers(env.order(days=12)["lines"][0]) == (0, 0, 25)


def test_deleting_a_growing_cycle_brings_the_activity_back(env):
    env.shelf(10)
    env.cycle(-100, status="harvested", harvest_quantity_kg=25, harvest_date=day(-50))
    cycle = env.cycle(-32, table=2)
    env.order(days=12)
    assert env.pending() == []
    assert env.client.delete(f"/crop-cycles/{cycle['id']}").status_code == 204
    assert len(env.pending()) == 1


def test_cycle_created_for_a_line_is_reserved_for_it(env):
    env.shelf(10)
    env.cycle(-100, status="harvested", harvest_quantity_kg=30, harvest_date=day(-50))
    order = env.order(days=50)
    env.done(order)
    env.post(f"/sales-orders/lines/{order['lines'][0]['id']}/planting",
             {"table_ids": [2], "nursery_start": day(0)})
    earlier = env.order(days=45)
    assert numbers(env.line(order)) == (0, 25, 0)
    assert numbers(env.line(earlier)) == (0, 5, 20)  # only the surplus is shared


def test_deleted_activity_is_not_recreated_by_replanning(env):
    order = env.order()
    env.client.delete(f"/tasks/{order['lines'][0]['planting_task_id']}")
    env.receive(1)
    assert env.pending() == []
    line = order["lines"][0]
    env.patch(f"/sales-orders/{order['id']}", {"lines": [{
        "id": line["id"], "product_id": env.product, "quantity": 26, "delivery_date": line["delivery_date"]}]})
    assert len(env.pending()) == 1


def test_daily_job_is_safe_and_idempotent(env):
    env.order()
    with env.Session() as db:
        replan_open_orders_job(db)
        replan_open_orders_job(db)
    assert len(env.pending()) == 1


def test_delivery_posts_document_stock_and_income_then_closes(env):
    env.receive(30)
    order = env.order(days=5)
    result = env.deliver(order, 25, unit_price=40)
    assert result["order"]["status"] == "delivered" and env.balance() == 5
    assert result["order"]["lines"][0]["planting_status"] == "delivered"
    document = env.get(f"/trade/documents/{result['document_id']}")
    assert (document["reference_no"], document["customer_id"]) == (order["order_no"], env.customer)
    assert env.pending() == []
    with env.Session() as db:
        entries = db.query(FinanceEntry).all()
        assert [(entry.direction, entry.source_id) for entry in entries] == [("income", document["id"])]


def test_partial_delivery_keeps_order_open(env):
    env.receive(30)
    order = env.order(days=5)
    result = env.deliver(order, 10)
    line = result["order"]["lines"][0]
    assert result["order"]["status"] == "open" and line["delivered_quantity"] == 10 and line["to_plant"] == 15
    env.deliver(order, 15.001, 409)
    assert env.deliver(order, 15)["order"]["status"] == "delivered"


def test_voiding_delivery_reopens_order(env):
    env.receive(30)
    order = env.order(days=5)
    result = env.deliver(order, 25)
    env.post(f"/trade/documents/{result['document_id']}/void", {"reason": "ผิด"}, 200)
    reopened = env.get(f"/sales-orders/{order['id']}")
    assert reopened["status"] == "open" and reopened["lines"][0]["delivered_quantity"] == 0
    assert env.balance() == 30 and len(env.pending()) == 1


def test_bad_delivery_changes_nothing(env):
    env.receive(30)
    order = env.order(days=5)
    env.post(f"/sales-orders/{order['id']}/deliver", {"lines": [
        {"line_id": order["lines"][0]["id"], "quantity": 5}, {"line_id": 999, "quantity": 1}]}, 422)
    env.post(f"/sales-orders/{order['id']}/deliver", {"lines": [
        {"line_id": order["lines"][0]["id"], "quantity": 5}] * 2}, 422)
    assert env.balance() == 30 and env.line(order)["delivered_quantity"] == 0
    env.post(f"/sales-orders/{order['id']}/close", {"status": "cancelled"}, 200)
    env.deliver(order, 1, 409)


def test_delivered_line_cannot_shrink_or_disappear(env):
    env.receive(30)
    order = env.order(days=5)
    env.deliver(order, 10)
    line = order["lines"][0]
    item = {"product_id": env.product, "quantity": 9, "delivery_date": line["delivery_date"]}
    env.patch(f"/sales-orders/{order['id']}", {"lines": [{**item, "id": line["id"]}]}, 409)
    env.patch(f"/sales-orders/{order['id']}", {"lines": [item]}, 409)
