"""Build a demo database full of example farm data, to see how every page behaves.

Usage, from backend/:
    ../.venv/Scripts/python -m scripts.seed_demo            # creates demo.db at the repository root
    ../.venv/Scripts/python -m scripts.seed_demo other.db --replace

Everything goes through the real API, so stock, finance, orders and tasks are linked exactly as when
someone uses the app. Dates are relative to today. The data is encrypted with ENCRYPTION_KEY from .env,
so open the database with the same .env. It refuses to run when APP_ENV is production.
"""
import argparse
import os
import sys
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("database", nargs="?", default="demo.db", help="file to create (relative to the repository root)")
    parser.add_argument("--replace", action="store_true", help="delete the file first if it exists")
    return parser.parse_args()


def prepare_database(name: str, replace: bool) -> Path:
    path = Path(name)
    path = path if path.is_absolute() else PROJECT_ROOT / path
    if path.resolve() == (PROJECT_ROOT / "erp.db").resolve():
        sys.exit("Refusing to write demo data into erp.db; choose another file name.")
    if path.exists():
        if not replace:
            sys.exit(f"{path} already exists; add --replace to rebuild it.")
        for suffix in ("", "-shm", "-wal"):
            Path(f"{path}{suffix}").unlink(missing_ok=True)
    # Settings and the engine are created on import, so point them at the demo file first.
    os.environ["DATABASE_URL"] = "sqlite:///" + path.as_posix()
    return path


class NoScheduler:
    """Stands in for the background scheduler: the demo build needs no weather downloads or nightly jobs."""
    running = False

    def __getattr__(self, _name):
        return lambda *args, **kwargs: None


def main():
    import logging

    logging.getLogger("httpx").setLevel(logging.WARNING)
    args = parse_args()
    path = prepare_database(args.database, args.replace)

    from fastapi.testclient import TestClient

    from app import main as app_main
    from app.config import get_settings
    from app.database import SessionLocal
    from app.models import Insight, Role, User, WeatherLog
    from app.security import get_current_user
    from app.services.order_supply import today_bangkok
    from app.services.secure_fields import encrypt_text
    from app.services.weather import decode_weather_code

    if get_settings().app_env.strip().lower() == "production":
        sys.exit("Refusing to build demo data with APP_ENV=production.")

    app_main.scheduler = NoScheduler()
    app_main.run_weather_catchup_job = lambda: None
    app_main.log_registered_weather_jobs = lambda *_: None
    today = today_bangkok()

    def day(offset: int) -> str:
        return str(today + timedelta(days=offset))

    with TestClient(app_main.app) as client:
        with SessionLocal() as db:
            owner = db.query(User).filter(User.role == Role.owner).first()
            db.expunge(owner)
        app_main.app.dependency_overrides[get_current_user] = lambda: owner

        def call(method: str, url: str, body=None):
            response = client.request(method, url, json=body)
            if response.status_code >= 400:
                sys.exit(f"{method} {url} failed ({response.status_code}): {response.text}")
            return response.json() if response.content else None

        post = lambda url, body=None: call("POST", url, body if body is not None else {})  # noqa: E731
        patch = lambda url, body: call("PATCH", url, body)  # noqa: E731
        put = lambda url, body: call("PUT", url, body)  # noqa: E731

        # The default seed adds future sample cycles; the demo builds its own history instead.
        for cycle in call("GET", "/crop-cycles"):
            call("DELETE", f"/crop-cycles/{cycle['id']}")

        # Items in the warehouse, by type.
        def item(category, name, unit, reorder=None):
            return post("/products", {"category": category, "name": name, "unit": unit, "reorder_point": reorder})["id"]

        green = item("vegetable", "กรีนโอ๊ค", "kg")
        red = item("vegetable", "เรดโอ๊ค", "kg")
        frilly = item("vegetable", "ฟริลไอซ์เบิร์ก", "kg")
        # Seeds come in bags of about 400 but are counted one by one.
        seed_green = item("seed", "เมล็ดกรีนโอ๊ค", "เมล็ด", 2000)
        seed_red = item("seed", "เมล็ดเรดโอ๊ค", "เมล็ด", 800)
        fert_a = item("fertilizer", "ปุ๋ย A", "ลิตร", 10)
        fert_b = item("fertilizer", "ปุ๋ย B", "ลิตร", 10)
        neem = item("chemical", "สารสะเดา", "มล.", 200)
        sponge = item("blend", "ฟองน้ำเพาะกล้า", "แผ่น", 100)
        bags = item("other", "ถุงบรรจุผัก", "ใบ", 200)
        crop_products = {"Green Oak": green, "Red Oak": red, "Frilly": frilly}
        crop_types = {crop["name"]: crop["id"] for crop in call("GET", "/crop-types")}
        for name, product in crop_products.items():
            patch(f"/crop-types/{crop_types[name]}/product-mapping", {"product_id": product})
        for name, seed in {"Green Oak": seed_green, "Red Oak": seed_red}.items():
            patch(f"/crop-types/{crop_types[name]}", {"seed_product_id": seed})
        for product in crop_products.values():
            put(f"/freshness/products/{product}", {"shelf_life_days": 5, "warn_days": 1})

        # People the farm buys from and sells to.
        shop = post("/suppliers", {"name": "ร้านเกษตรสันทราย", "contact": "053-000-111", "area": "สันทราย เชียงใหม่"})["id"]
        fertiliser_co = post("/suppliers", {"name": "บริษัทปุ๋ยไทย", "contact": "02-000-2222", "note": "ส่งฟรีเมื่อซื้อครบ 2,000 บาท"})["id"]
        salad = post("/customers", {"name": "ร้านสลัดเชียงใหม่", "contact": "081-111-1111", "area": "นิมมานเหมินท์"})["id"]
        market = post("/customers", {"name": "ตลาดจริงใจ", "contact": "082-222-2222", "area": "ถนนโชตนา"})["id"]
        hotel = post("/customers", {"name": "โรงแรมริมปิง", "contact": "083-333-3333", "area": "ริมแม่น้ำปิง"})["id"]
        retail = post("/customers", {"name": "คุณสมศรี (ลูกค้าปลีก)", "contact": "084-444-4444"})["id"]

        # Buying supplies; the last purchase is left without an expense entry to show "ยังไม่ลงบัญชี".
        def receive(offset, supplier, lines, record_finance=True, reference=None):
            return post("/trade/inbound", {
                "doc_date": day(offset), "supplier_id": supplier, "reference_no": reference, "record_finance": record_finance,
                "lines": [{"product_id": product, "quantity": quantity, "unit_price": price} for product, quantity, price in lines],
            })

        receive(-62, shop, [(seed_green, 8000, "0.09"), (seed_red, 4800, "0.09"), (sponge, 300, "1.5")], reference="INV-6801")
        receive(-45, fertiliser_co, [(fert_a, 20, "120"), (fert_b, 20, "110"), (neem, 1000, "0.5")], reference="PT-2231")
        mistake = receive(-44, fertiliser_co, [(fert_a, 5, "120")], reference="PT-2232")
        post(f"/trade/documents/{mistake['id']}/void", {"reason": "บันทึกซ้ำกับ PT-2231"})
        receive(-10, shop, [(bags, 500, "0.8")], record_finance=False, reference="INV-6950")

        # Crop cycles at every stage. Past dates create tasks, some of them overdue.
        stages = [
            # table, crop, nursery start, final status, harvest kg
            (10, "Green Oak", -60, "harvested", 8.5),
            (11, "Red Oak", -55, "harvested", 7.2),
            (12, "Frilly", -50, "harvested", 9.0),
            (13, "Green Oak", -45, "harvested", 6.8),
            (14, "Red Oak", -43, "harvested", 5.5),
            (15, "Frilly", -41, "harvesting", 2.5),
            (16, "Green Oak", -30, "bushed", None),
            (17, "Red Oak", -25, "bushed", None),
            (18, "Frilly", -20, "bushed", None),
            (19, "Green Oak", -10, "nursery", None),
            (20, "Red Oak", -5, "nursery", None),
            (21, "Frilly", -2, "nursery", None),
        ]
        tables = {table["table_number"]: table["id"] for table in call("GET", "/tables")}
        batch = call("GET", "/batches")[0]["id"]
        cycles = {}
        for table, crop, start, status, harvest in stages:
            cycle = post("/crop-cycles", {
                "table_id": tables[table], "batch_id": batch, "crop_type_id": crop_types[crop], "nursery_start": day(start),
                "seed_count": 220, "create_tasks": True,
            })["id"]
            cycles[table] = cycle
            if status != "nursery":
                post(f"/crop-cycles/{cycle}/status", {"status": "bushed", "on_date": day(start + 14), "plant_count": 190 + table % 7})
            if status in ("ready_to_harvest", "harvesting", "harvested"):
                patch(f"/crop-cycles/{cycle}", {"status": "ready_to_harvest"})
            if status == "harvesting":
                post(f"/crop-cycles/{cycle}/harvests", {"harvested_on": day(-1), "quantity_kg": harvest})
            if status == "harvested":
                # Picked over two days, as the farm usually does.
                first = round(harvest * 0.6, 1)
                post(f"/crop-cycles/{cycle}/harvests", {"harvested_on": day(start + 41), "quantity_kg": first})
                post(f"/crop-cycles/{cycle}/harvests", {"harvested_on": day(start + 42), "quantity_kg": round(harvest - first, 1), "final": True})

        # Fertiliser and spray activities, which also take stock out.
        def apply(tables_used, offset, kind, items, note=None, status="done"):
            body = {
                "kind": kind, "status": status, "cycle_ids": [cycles[table] for table in tables_used], "note": note,
                "items": [{"item_name": name, "quantity": quantity, "unit": unit, "product_id": product} for name, quantity, unit, product in items],
            }
            body["done_on" if status == "done" else "planned_date"] = day(offset)
            post("/activities", body)

        apply([16, 17], -14, "fertilize", [("ปุ๋ย A", 4, "ลิตร", fert_a), ("ปุ๋ย B", 3, "ลิตร", fert_b)])
        apply([17], -9, "fertilize", [("ปุ๋ย A", 2, "ลิตร", fert_a), ("ปุ๋ย B", 2, "ลิตร", fert_b)])
        apply([18], -4, "spray", [("สารสะเดา", 50, "มล.", neem)], note="พบเพลี้ยเล็กน้อยที่ขอบโต๊ะ")
        apply([15], -20, "fertilize", [("ปุ๋ย A", 1.5, "ลิตร", fert_a), ("น้ำหมักชีวภาพ", 1, "ลิตร", None)])
        apply([16, 17, 18], 2, "spray", [("สารสะเดา", 120, "มล.", neem)], note="ฉีดกันเพลี้ยรอบถัดไป", status="pending")

        # Sales, a giveaway, and spoiled produce.
        def send(offset, customer, lines, purpose="sale", note=None, record_finance=None):
            body = {"doc_date": day(offset), "customer_id": customer, "purpose": purpose, "note": note,
                    "lines": [{"product_id": product, "quantity": quantity, "unit_price": price} for product, quantity, price in lines]}
            if record_finance is not None:
                body["record_finance"] = record_finance
            return post("/trade/outbound", body)

        send(-15, salad, [(green, 5, "80")])
        send(-8, market, [(red, 4, "90")])
        send(-5, None, [(green, 0.5, None)], purpose="other", note="แจกตัวอย่างให้ร้านค้าใหม่")
        send(-2, retail, [(frilly, 1.5, "100")], record_finance=False)
        green_lots = [lot for lot in call("GET", "/freshness/lots")["items"] if lot["product_id"] == green]
        expired = min(green_lots, key=lambda lot: lot["expires_on"], default=None)
        if expired:
            post("/freshness/waste", {"product_id": green, "lot_key": expired["lot_key"], "quantity": "1", "reason": "expired",
                                      "note": "ใบเหลือง เก็บไว้นานเกินไป"})

        # Customer orders: delivered, part-delivered, planned, planted by hand, and cancelled.
        def order(customer, lines, **extra):
            return post("/sales-orders", {"customer_id": customer, "lines": [
                {"product_id": product, "quantity": quantity, "delivery_date": day(offset), "unit_price": price}
                for product, quantity, offset, price in lines
            ], **extra})

        done = order(salad, [(green, 3, 2, "80")], note="ส่งก่อน 10 โมง")
        post(f"/sales-orders/{done['id']}/deliver", {"lines": [{"line_id": done["lines"][0]["id"], "quantity": 3, "use_order_price": True}]})
        partial = order(hotel, [(red, 10, 5, "85")])
        post(f"/sales-orders/{partial['id']}/deliver", {"lines": [{"line_id": partial["lines"][0]["id"], "quantity": 4, "use_order_price": True}]})
        order(market, [(green, 20, 45, "75"), (frilly, 8, 45, "95")])
        order(salad, [(red, 12, 60, "85")], auto_planting=False)
        cancelled = order(retail, [(green, 2, 10, "90")])
        post(f"/sales-orders/{cancelled['id']}/close", {"status": "cancelled"})

        # Day-to-day farm work and costs.
        post("/activities", {"kind": "general", "title": "ล้างถังสารละลาย", "status": "pending", "planned_date": day(-2)})
        post("/activities", {"kind": "general", "title": "ตรวจค่า EC และ pH", "status": "pending", "planned_date": day(1)})
        post("/activities", {"kind": "general", "title": "ซ่อมท่อน้ำโต๊ะ 12", "done_on": day(-6), "table_ids": [tables[12]],
                             "labor_cost": "300", "worker_count": 1})
        for entry_date, direction, category, amount, description in [
            (-25, "expense", "equipment", "1500", "ปั๊มน้ำตัวใหม่"),
            (-20, "expense", "utilities", "850", "ค่าไฟเดือนนี้"),
            (-12, "expense", "labor", "1200", "ค่าแรงช่วยเก็บผัก 3 วัน"),
            (-6, "expense", "transport", "300", "ค่าน้ำมันส่งของ"),
            (-3, "income", "other", "250", "ขายต้นกล้าให้เพื่อนบ้าน"),
        ]:
            post("/finance/entries", {"entry_date": day(entry_date), "direction": direction, "category": category,
                                      "amount": amount, "description": description})

        # Notes from the system, and past weather (the forecast itself still comes from the internet).
        with SessionLocal() as db:
            for kind, severity, title, body in [
                ("alert", "high", "เรดโอ๊คในคลังใกล้หมดอายุ", "ล็อตที่เก็บเมื่อวานจะหมดอายุในอีก 4 วัน ควรส่งออเดอร์ของโรงแรมริมปิงให้ครบก่อน"),
                ("recommendation", "medium", "ควรเพาะกรีนโอ๊คเพิ่ม 1 โต๊ะ", "ออเดอร์ของตลาดจริงใจต้องการ 20 กก. ในอีก 45 วัน แต่โต๊ะที่ปลูกอยู่ให้ผลผลิตไม่พอ"),
                ("insight", "low", "ยอดขายเดือนนี้มาจากร้านสลัดมากที่สุด", "ร้านสลัดเชียงใหม่สั่งรวม 8 กก. คิดเป็นราว 40% ของยอดขายผักเดือนนี้"),
            ]:
                db.add(Insight(kind=kind, source="manual", severity=severity, status="new",
                               title_encrypted=encrypt_text(title).encode("ascii"),
                               body_encrypted=encrypt_text(body).encode("ascii"),
                               valid_from=datetime.now(timezone.utc)))
            codes = [0, 1, 2, 3, 61, 80, 2, 1, 0, 63, 95, 3]
            for offset in range(1, 31):
                log_date = today - timedelta(days=offset)
                code = codes[offset % len(codes)]
                db.add(WeatherLog(log_date=log_date, temp_min=17 + offset % 4, temp_max=28 + offset % 5,
                                  humidity=60 + (offset * 7) % 30, rainfall=0.0 if code < 61 else 4.5 + offset % 6,
                                  condition=decode_weather_code(code),
                                  fetched_at=datetime.combine(log_date, time(8, 0))))
            db.commit()

        app_main.app.dependency_overrides.clear()

    print(f"Demo database ready: {path}")


if __name__ == "__main__":
    main()
