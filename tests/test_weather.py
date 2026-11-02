from datetime import date, datetime
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import Role, User, WeatherLog
from app.security import hash_password
from app.services.weather import fetch_and_save_weather_for_date, sync_yesterday_weather


def build_test_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return engine, SessionLocal


MOCK_OPEN_METEO_RESPONSE = {
    "daily": {
        "time": ["2026-09-21"],
        "temperature_2m_max": [32.5],
        "temperature_2m_min": [22.0],
        "precipitation_sum": [4.5],
        "weather_code": [61],
    },
    "hourly": {
        "time": [f"2026-09-21T{h:02d}:00" for h in range(24)],
        "relative_humidity_2m": [80.0] * 24,
    },
}

MOCK_FORECAST_RESPONSE = {
    "daily": {
        "time": [f"2026-09-{d:02d}" for d in range(22, 29)],
        "temperature_2m_max": [31.0 + i * 0.2 for i in range(7)],
        "temperature_2m_min": [23.0 + i * 0.1 for i in range(7)],
        "precipitation_sum": [1.0, 0.0, 5.2, 12.0, 0.0, 2.1, 0.5],
        "weather_code": [0, 1, 61, 95, 2, 80, 51],
    },
    "hourly": {
        "time": [f"2026-09-{d:02d}T{h:02d}:00" for d in range(22, 29) for h in range(24)],
        "relative_humidity_2m": [75.0] * (7 * 24),
    },
}


def test_weather_upsert_idempotency():
    _, SessionLocal = build_test_db()
    target_date = date(2026, 9, 21)

    with patch("app.services.weather.httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.json.return_value = MOCK_OPEN_METEO_RESPONSE
        mock_resp.raise_for_status.return_value = None
        mock_client.get.return_value = mock_resp
        mock_client.__enter__.return_value = mock_client
        mock_client_cls.return_value = mock_client

        with SessionLocal() as db:
            # 1. First sync -> inserts 1 row
            log1 = fetch_and_save_weather_for_date(db, target_date)
            assert log1.log_date == target_date
            assert log1.temp_max == 32.5
            assert log1.temp_min == 22.0
            assert log1.rainfall == 4.5
            assert log1.humidity == 80.0
            assert log1.condition == "ฝนตกเล็กน้อย"

            count1 = db.scalar(select(WeatherLog).where(WeatherLog.log_date == target_date))
            assert count1 is not None

            # 2. Second sync on same day with updated data -> must update, not insert duplicate row
            updated_response = {
                "daily": {
                    "time": ["2026-09-21"],
                    "temperature_2m_max": [33.0],
                    "temperature_2m_min": [21.5],
                    "precipitation_sum": [6.0],
                    "weather_code": [63],
                },
                "hourly": {
                    "time": [f"2026-09-21T{h:02d}:00" for h in range(24)],
                    "relative_humidity_2m": [82.0] * 24,
                },
            }
            mock_resp.json.return_value = updated_response

            log2 = fetch_and_save_weather_for_date(db, target_date)
            assert log2.id == log1.id
            assert log2.temp_max == 33.0
            assert log2.rainfall == 6.0
            assert log2.condition == "ฝนตกปานกลาง"

            all_logs = db.scalars(select(WeatherLog).where(WeatherLog.log_date == target_date)).all()
            assert len(all_logs) == 1, "There must be exactly 1 row for target_date"


def test_weather_endpoints_and_history():
    _, SessionLocal = build_test_db()

    with SessionLocal() as db:
        user = User(username="weather_user", password_hash=hash_password("owner123"), role=Role.owner)
        db.add(user)
        # Pre-seed historical WeatherLogs
        db.add_all([
            WeatherLog(
                log_date=date(2026, 9, 19),
                temp_min=22.0,
                temp_max=31.0,
                humidity=80.0,
                rainfall=0.0,
                condition="ท้องฟ้าแจ่มใส",
                fetched_at=datetime.utcnow(),
            ),
            WeatherLog(
                log_date=date(2026, 9, 20),
                temp_min=23.0,
                temp_max=30.0,
                humidity=85.0,
                rainfall=12.0,
                condition="พายุฝนฟ้าคะนอง",
                fetched_at=datetime.utcnow(),
            ),
        ])
        db.commit()

    def override_get_db():
        with SessionLocal() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    login_resp = client.post("/auth/login", json={"username": "weather_user", "password": "owner123"})
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Test GET /weather/forecast with mocked Open-Meteo
    with patch("app.services.weather.httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.json.return_value = MOCK_FORECAST_RESPONSE
        mock_resp.raise_for_status.return_value = None
        mock_client.get.return_value = mock_resp
        mock_client.__enter__.return_value = mock_client
        mock_client_cls.return_value = mock_client

        forecast_resp = client.get("/weather/forecast?days=7", headers=headers)
        assert forecast_resp.status_code == 200
        days = forecast_resp.json()
        assert len(days) == 7
        assert "temp_min" in days[0]
        assert "temp_max" in days[0]
        assert "humidity" in days[0]
        assert "rainfall" in days[0]
        assert "condition" in days[0]

    # 2. Test GET /weather/history
    hist_resp = client.get("/weather/history", headers=headers)
    assert hist_resp.status_code == 200
    hist = hist_resp.json()
    assert len(hist) == 2
    assert hist[0]["log_date"] == "2026-09-20"  # sorted desc

    # 3. Test GET /weather/history with date filter
    filtered_resp = client.get("/weather/history?from=2026-09-20", headers=headers)
    assert len(filtered_resp.json()) == 1
    assert filtered_resp.json()[0]["log_date"] == "2026-09-20"

    # 4. Test POST /weather/sync-yesterday
    with patch("app.services.weather.httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.json.return_value = MOCK_OPEN_METEO_RESPONSE
        mock_resp.raise_for_status.return_value = None
        mock_client.get.return_value = mock_resp
        mock_client.__enter__.return_value = mock_client
        mock_client_cls.return_value = mock_client

        sync_resp = client.post("/weather/sync-yesterday", headers=headers)
        assert sync_resp.status_code == 200
        assert "สำเร็จ" in sync_resp.json()["message"]
        assert sync_resp.json()["log"] is not None

    app.dependency_overrides.clear()
