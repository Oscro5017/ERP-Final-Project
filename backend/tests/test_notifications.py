"""Phase 3 step 5: morning reminders in the app and summary pushes to the owner's phone."""
import json
from datetime import date, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import Activity, Notification, Product, ProductShelfLife, PushDevice, Role, StockMovement, User
from app.security import get_current_user
from app.services.notifications import build_reminders, register_device, run_morning_reminders, send_pushes
from app.services.push_fcm import FcmSender, InvalidDeviceToken, PushNotConfigured
from app.services.secure_fields import encrypt_text, hash_catalog_name

TODAY = date(2026, 12, 1)


def make_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False)
    with Session() as db:
        db.add_all([
            User(id=1, username="owner", password_hash="x", role=Role.owner),
            User(id=2, username="dev", password_hash="x", role=Role.developer),
            Activity(id=1, kind="spray", title=encrypt_text("ฉีดสะเดาโต๊ะ 3"), is_encrypted=True, source="manual",
                     planned_date=date(2026, 12, 3), remind=True),
            Activity(id=2, kind="general", title="ล้างถัง", source="auto", planned_date=TODAY, remind=True),
            Activity(id=3, kind="general", title="ไม่ต้องเตือน", source="auto", planned_date=TODAY, remind=False),
            Activity(id=4, kind="general", title="ทำแล้ว", source="auto", planned_date=TODAY, remind=True, status="done"),
            Activity(id=5, kind="general", title="อีก 5 วัน", source="auto", planned_date=date(2026, 12, 6), remind=True),
        ])
        db.commit()
    return Session


class FakeSender:
    def __init__(self):
        self.sent = []

    def send(self, token, title, body, data=None):
        if token.startswith("dead"):
            raise InvalidDeviceToken("gone")
        self.sent.append((token, title, body, data))


def test_reminders_cover_due_and_upcoming_planned_work_once():
    Session = make_db()
    with Session() as db:
        assert build_reminders(db, TODAY, lead_days=2) == 2
        assert build_reminders(db, TODAY, lead_days=2) == 0
        db.commit()
        rows = db.scalars(select(Notification).order_by(Notification.activity_id)).all()
        assert [(row.user_id, row.activity_id, row.kind) for row in rows] == [(1, 1, "activity_due"), (1, 2, "activity_due")]
        assert b"\xe0\xb8" not in rows[0].title_encrypted  # Thai text is not stored in the clear


def test_expiring_lots_are_reminded_in_their_warning_window():
    Session = make_db()
    with Session() as db:
        db.add(Product(id=1, category="vegetable", name_encrypted=encrypt_text("คะน้า").encode(), name_hash=hash_catalog_name("คะน้า"), unit="kg"))
        db.flush()
        db.add(ProductShelfLife(product_id=1, shelf_life_days=5, warn_days=1))
        db.add(StockMovement(product_id=1, quantity_delta=3, movement_type="receipt", occurred_at=datetime(2026, 11, 26, 3)))
        db.commit()
        # Received 26 Nov, kept 5 days, warned 1 day before: reminded from 30 Nov.
        build_reminders(db, TODAY - timedelta(days=2), lead_days=2)
        assert db.scalar(select(Notification).where(Notification.kind == "lot_expiring")) is None
        build_reminders(db, TODAY, lead_days=2)
        lot = db.scalar(select(Notification).where(Notification.kind == "lot_expiring"))
        assert lot is not None and lot.product_id == 1


def test_push_is_a_summary_without_farm_details_and_bad_tokens_are_dropped():
    Session = make_db()
    sender = FakeSender()
    with Session() as db:
        register_device(db, 1, "phone-token-aaaaaaaaaaaaaaaaaaaa")
        register_device(db, 1, "dead-token-bbbbbbbbbbbbbbbbbbbbbb")
        build_reminders(db, TODAY, lead_days=2)
        assert send_pushes(db, sender) == 1
        db.commit()
        [(token, title, body, data)] = sender.sent
        assert token == "phone-token-aaaaaaaaaaaaaaaaaaaa"
        assert "2 รายการ" in body and "สะเดา" not in title + body and data == {"kind": "reminders", "count": "2"}
        assert all(row.sent_at is not None for row in db.scalars(select(Notification)))
        assert [d.user_id for d in db.scalars(select(PushDevice))] == [1]
        assert send_pushes(db, sender) == 0  # nothing new


def test_without_firebase_or_a_phone_reminders_stay_in_the_app():
    Session = make_db()
    with Session() as db:
        settings = SimpleNamespace(notify_lead_days=2, fcm_credentials_file=None)
        assert run_morning_reminders(db, settings, today=TODAY) == 2
        assert {row.push_error for row in db.scalars(select(Notification))} == {"push_not_configured"}
    Session = make_db()
    with Session() as db:
        build_reminders(db, TODAY)
        send_pushes(db, FakeSender())
        assert {row.push_error for row in db.scalars(select(Notification))} == {"no_device"}


def test_notification_api_lists_marks_read_and_registers_phones():
    Session = make_db()
    with Session() as db:
        build_reminders(db, TODAY)
        db.commit()

    def override_db():
        with Session() as db:
            yield db

    role = {"value": Role.owner}
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: User(id=1 if role["value"] == Role.owner else 2, username="u", password_hash="x", role=role["value"])
    try:
        client = TestClient(app)
        rows = client.get("/notifications?unread=true").json()
        assert sorted(row["title"] for row in rows) == ["วันนี้: ล้างถัง", "อีก 2 วัน: ฉีดสะเดาโต๊ะ 3"]
        assert client.post(f"/notifications/{rows[0]['id']}/read").json()["read_at"] is not None
        assert len(client.get("/notifications?unread=true").json()) == 1
        assert client.post("/notifications/read-all").status_code == 204
        assert client.get("/notifications?unread=true").json() == []

        token = "fcm-token-cccccccccccccccccccccccc"
        assert client.post("/push-devices", json={"token": token}).status_code == 204
        assert client.post("/push-devices", json={"token": token}).status_code == 204
        with Session() as db:
            assert len(db.scalars(select(PushDevice)).all()) == 1
            assert token.encode() not in db.scalar(select(PushDevice.token_encrypted))
        assert client.post("/push-devices/remove", json={"token": token}).status_code == 204

        role["value"] = Role.developer
        assert client.get("/notifications").json() == []  # reminders belong to the owner
        assert client.post(f"/notifications/{rows[0]['id']}/read").status_code == 404
    finally:
        app.dependency_overrides.clear()


def _service_account(tmp_path):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
    path = tmp_path / "firebase.json"
    path.write_text(json.dumps({"project_id": "farm-test", "client_email": "push@farm-test.iam", "private_key": pem}))
    return path


def test_fcm_sender_gets_a_token_and_sends_one_message(tmp_path):
    calls = []

    def handler(request: httpx.Request):
        calls.append(request)
        if request.url.host == "oauth2.googleapis.com":
            assert b"grant_type=urn" in request.content
            return httpx.Response(200, json={"access_token": "ya29.test", "expires_in": 3600})
        if b"dead" in request.content:
            return httpx.Response(404, json={"error": {"status": "NOT_FOUND"}})
        assert request.headers["Authorization"] == "Bearer ya29.test"
        assert request.url.path == "/v1/projects/farm-test/messages:send"
        return httpx.Response(200, json={"name": "projects/farm-test/messages/1"})

    sender = FcmSender(str(_service_account(tmp_path)), client=httpx.Client(transport=httpx.MockTransport(handler)))
    sender.send("good-token", "งานฟาร์มวันนี้", "มี 2 รายการ")
    sender.send("good-token", "งานฟาร์มวันนี้", "มี 1 รายการ")
    assert [c.url.host for c in calls] == ["oauth2.googleapis.com", "fcm.googleapis.com", "fcm.googleapis.com"]
    message = json.loads(calls[1].content)["message"]
    assert message["token"] == "good-token" and message["notification"]["title"] == "งานฟาร์มวันนี้"
    with pytest.raises(InvalidDeviceToken):
        sender.send("dead-token", "x", "y")


def test_fcm_sender_needs_a_key_file(tmp_path):
    with pytest.raises(PushNotConfigured):
        FcmSender(None)
    with pytest.raises(PushNotConfigured):
        FcmSender(str(tmp_path / "missing.json"))
