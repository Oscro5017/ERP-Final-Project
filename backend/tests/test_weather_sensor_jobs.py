from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.main as main
from app.database import Base, get_db
from app.main import app
from app.models import ForecastSnapshot, Role, SensorReading, User, WeatherLog
from app.security import create_access_token, hash_password
from app.services import weather


def build_test_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return engine, SessionLocal


def override_database(SessionLocal):
    def override_get_db():
        with SessionLocal() as db:
            yield db
    app.dependency_overrides[get_db] = override_get_db


def forecast_day(target_date, temperature=31.0):
    return {
        "date": target_date,
        "temp_min": temperature - 8,
        "temp_max": temperature,
        "humidity": 76.0,
        "precip_probability": 30.0,
        "rainfall": 1.5,
        "condition": "มีเมฆบางส่วน",
        "weather_code": 2,
    }


def test_forecast_snapshot_upsert_updates_same_issue_date():
    _, SessionLocal = build_test_db()
    issue_time = datetime(2026, 10, 30, 8, 5, tzinfo=UTC)
    day = forecast_day(date(2026, 10, 31))

    with SessionLocal() as db, patch("app.services.weather.get_live_forecast", return_value=[day]):
        first = weather.capture_forecast_snapshots(db, issued_at=issue_time)
        day["temp_max"] = 35.0
        second = weather.capture_forecast_snapshots(db, issued_at=issue_time + timedelta(minutes=1))
        rows = db.scalars(select(ForecastSnapshot)).all()

    assert len(first) == len(second) == 1
    assert first[0].id == second[0].id
    assert len(rows) == 1
    assert rows[0].temp_max == 35.0
    assert rows[0].lead_days == 1


def test_scheduled_forecast_job_contains_open_meteo_failure(monkeypatch):
    _, SessionLocal = build_test_db()
    monkeypatch.setattr(main, "SessionLocal", lambda: SessionLocal())

    def fail_fetch(_db):
        raise RuntimeError("Open-Meteo unavailable")

    monkeypatch.setattr(main, "capture_forecast_snapshots", fail_fetch)
    assert main.run_forecast_snapshot_job() is None


def test_weather_catchup_fills_only_missing_days_and_tolerates_failures(monkeypatch):
    _, SessionLocal = build_test_db()
    today = date(2026, 10, 30)
    existing_date = today - timedelta(days=2)
    requested = []

    with SessionLocal() as db:
        db.add(WeatherLog(
            log_date=existing_date,
            temp_min=20,
            temp_max=30,
            humidity=70,
            rainfall=0,
            condition="clear",
            fetched_at=datetime.utcnow(),
        ))
        db.commit()

        def fake_fetch(session, target_date):
            requested.append(target_date)
            if target_date == today - timedelta(days=4):
                raise RuntimeError("network unavailable")
            row = WeatherLog(
                log_date=target_date,
                temp_min=20,
                temp_max=30,
                humidity=70,
                rainfall=0,
                condition="clear",
                fetched_at=datetime.utcnow(),
            )
            session.add(row)
            session.commit()
            return row

        monkeypatch.setattr(weather, "fetch_and_save_weather_for_date", fake_fetch)
        synced = weather.catch_up_weather_history(db, today=today)
        assert synced == 12
        assert len(requested) == 13
        assert existing_date not in requested
        assert db.query(WeatherLog).count() == 13

        monkeypatch.setattr(weather, "fetch_and_save_weather_for_date", lambda *_: (_ for _ in ()).throw(RuntimeError("offline")))
        assert weather.catch_up_weather_history(db, today=today) == 0
        assert db.query(WeatherLog).count() == 13


def test_sensor_device_token_batch_upsert_validation_and_jwt_read(monkeypatch):
    _, SessionLocal = build_test_db()
    with SessionLocal() as db:
        user = User(username="sensor_reader", password_hash=hash_password("reader123"), role=Role.owner)
        db.add(user)
        db.commit()
        token = create_access_token(user)

    override_database(SessionLocal)
    settings = SimpleNamespace(device_token="device-secret-test")
    monkeypatch.setattr("app.routers.sensors.get_settings", lambda: settings)
    client = TestClient(app)
    recorded_at = "2026-10-29T08:00:00+07:00"
    reading = {
        "device_id": "farm-sensor-1",
        "sensor_type": "humidity_pct",
        "value": 70,
        "unit": "%",
        "recorded_at": recorded_at,
    }

    assert client.get("/sensors/readings").status_code == 401
    assert client.post("/sensors/readings", json={"readings": [reading]}).status_code == 401
    wrong_token = client.post("/sensors/readings", json={"readings": [reading]}, headers={"X-Device-Token": "wrong"})
    assert wrong_token.status_code == 401

    batch = client.post(
        "/sensors/readings",
        json={"readings": [reading, {**reading, "value": 75}]},
        headers={"X-Device-Token": settings.device_token},
    )
    assert batch.status_code == 200
    assert batch.json() == {"accepted_count": 1, "updated_count": 1}
    assert client.get("/sensors/readings", headers={"Authorization": f"Bearer {token}"}).json()[0]["value"] == 75

    invalid_batch = client.post(
        "/sensors/readings",
        json={"readings": [reading, {**reading, "sensor_type": "humidity_pct", "value": 101}]},
        headers={"X-Device-Token": settings.device_token},
    )
    assert invalid_batch.status_code == 422
    with SessionLocal() as db:
        assert db.query(SensorReading).count() == 1

    assert client.get("/sensors/readings", headers={"Authorization": f"Bearer {token}"}).status_code == 200
    app.dependency_overrides.clear()


def test_sensor_ingestion_is_disabled_without_device_token(monkeypatch):
    _, SessionLocal = build_test_db()
    override_database(SessionLocal)
    monkeypatch.setattr("app.routers.sensors.get_settings", lambda: SimpleNamespace(device_token=None))
    response = TestClient(app).post("/sensors/readings", json={"readings": [{
        "device_id": "farm-sensor-1",
        "sensor_type": "temperature_c",
        "value": 25,
        "unit": "C",
        "recorded_at": "2026-10-29T08:00:00+07:00",
    }]})
    assert response.status_code == 503
    app.dependency_overrides.clear()


def test_phase1e_tables_create_idempotently():
    engine, _ = build_test_db()
    Base.metadata.create_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    assert {"forecast_snapshots", "sensor_readings", "recommendations"}.issubset(
        set(Base.metadata.tables)
    )
    engine.dispose()