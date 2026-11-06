from datetime import date, datetime, timedelta
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import Role, User, WeatherLog
from app.security import hash_password
from app.services.weather import fetch_and_save_weather_for_date, sync_yesterday_weather
from app.services import weather as weather_service
import pytest


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
        "precipitation_probability_max": [10, 0, 35, 80, 5, 40, 20],
        "weather_code": [0, 1, 61, 95, 2, 80, 51],
    },
    "hourly": {
        "time": [f"2026-09-{d:02d}T{h:02d}:00" for d in range(22, 29) for h in range(24)],
        "relative_humidity_2m": [75.0] * (7 * 24),
    },
}


def test_weather_upsert_idempotency():
    weather_service.clear_forecast_cache()
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
    weather_service.clear_forecast_cache()
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
    assert hist[0]["source"] == "open-meteo-model"

    # 3. Test GET /weather/history with date filter
    filtered_resp = client.get("/weather/history?from=2026-09-20", headers=headers)
    assert len(filtered_resp.json()) == 1
    assert filtered_resp.json()[0]["log_date"] == "2026-09-20"

    # 4. Test POST /weather/sync-yesterday
    with patch("app.services.weather.httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_resp = MagicMock()
        yesterday = date.today() - timedelta(days=1)
        mock_resp.json.return_value = {
            "daily": {
                "time": [yesterday.isoformat()],
                "temperature_2m_max": [32.5],
                "temperature_2m_min": [22.0],
                "precipitation_sum": [4.5],
                "weather_code": [61],
            },
            "hourly": {
                "time": [f"{yesterday.isoformat()}T{hour:02d}:00" for hour in range(24)],
                "relative_humidity_2m": [80.0] * 24,
            },
        }
        mock_resp.raise_for_status.return_value = None
        mock_client.get.return_value = mock_resp
        mock_client.__enter__.return_value = mock_client
        mock_client_cls.return_value = mock_client

        sync_resp = client.post("/weather/sync-yesterday", headers=headers)
        assert sync_resp.status_code == 200
        assert "สำเร็จ" in sync_resp.json()["message"]
        assert sync_resp.json()["log"] is not None

    app.dependency_overrides.clear()


def test_incomplete_historical_day_is_skipped_without_inserting():
    _, SessionLocal = build_test_db()
    target_date = date(2026, 9, 21)
    incomplete = {"daily": {"time": [target_date.isoformat()], "temperature_2m_min": [20.0]}, "hourly": {}}
    with patch("app.services.weather.httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.json.return_value = incomplete
        mock_resp.raise_for_status.return_value = None
        mock_client.get.return_value = mock_resp
        mock_client.__enter__.return_value = mock_client
        mock_client_cls.return_value = mock_client
        with SessionLocal() as db:
            assert fetch_and_save_weather_for_date(db, target_date) is None
            assert db.scalars(select(WeatherLog)).all() == []


def test_forecast_skips_day_with_missing_required_values():
    weather_service.clear_forecast_cache()
    payload = {
        "daily": {
            "time": ["2026-09-21"], "temperature_2m_max": [None],
            "temperature_2m_min": [20.0], "precipitation_sum": [0.0],
            "precipitation_probability_max": [10], "weather_code": [1],
        },
        "hourly": {"time": ["2026-09-21T00:00"], "relative_humidity_2m": [70]},
    }
    with patch("app.services.weather.httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.json.return_value = payload
        mock_resp.raise_for_status.return_value = None
        mock_client.get.return_value = mock_resp
        mock_client.__enter__.return_value = mock_client
        mock_client_cls.return_value = mock_client
        assert weather_service.get_live_forecast() == []


def test_forecast_skips_empty_or_malformed_daily_arrays():
    weather_service.clear_forecast_cache()
    payloads = [
        {"daily": {"time": [], "temperature_2m_max": [], "temperature_2m_min": [], "precipitation_sum": [], "precipitation_probability_max": [], "weather_code": []}, "hourly": {}},
        {"daily": {"time": ["2026-09-21"], "temperature_2m_max": "31", "temperature_2m_min": [20], "precipitation_sum": [0], "precipitation_probability_max": [10], "weather_code": [1]}, "hourly": {"time": ["2026-09-21T00:00"], "relative_humidity_2m": [70]}},
    ]
    for payload in payloads:
        weather_service.clear_forecast_cache()
        with patch("app.services.weather.httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_resp = MagicMock()
            mock_resp.json.return_value = payload
            mock_resp.raise_for_status.return_value = None
            mock_client.get.return_value = mock_resp
            mock_client.__enter__.return_value = mock_client
            mock_client_cls.return_value = mock_client
            assert weather_service.get_live_forecast() == []


def test_forecast_upstream_timeout_is_not_cached():
    import httpx

    weather_service.clear_forecast_cache()
    with patch("app.services.weather.httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.get.side_effect = httpx.TimeoutException("upstream timeout")
        mock_client.__enter__.return_value = mock_client
        mock_client_cls.return_value = mock_client
        for _ in range(2):
            with pytest.raises(httpx.TimeoutException):
                weather_service.get_live_forecast(days=6)
        assert mock_client.get.call_count == 2


def test_forecast_ttl_cache_hit_expiry_and_error_not_cached(monkeypatch):
    weather_service.clear_forecast_cache()
    now = [100.0]
    calls = []
    settings = type("Settings", (), {
        "farm_latitude": 1.0, "farm_longitude": 2.0, "weather_forecast_cache_seconds": 900,
    })()
    monkeypatch.setattr(weather_service, "get_settings", lambda: settings)
    monkeypatch.setattr(weather_service.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(weather_service, "_fetch_live_forecast", lambda days: calls.append(days) or [{"date": date(2026, 9, 21)}])

    first = weather_service.get_live_forecast(7)
    first[0]["changed"] = True
    assert weather_service.get_live_forecast(7) == [{"date": date(2026, 9, 21)}]
    assert calls == [7]
    now[0] += 901
    weather_service.get_live_forecast(7)
    assert calls == [7, 7]

    weather_service.clear_forecast_cache()
    failures = [0]
    def fail_once(_days):
        failures[0] += 1
        if failures[0] == 1:
            raise RuntimeError("upstream secret detail")
        return [{"date": date(2026, 9, 21)}]
    monkeypatch.setattr(weather_service, "_fetch_live_forecast", fail_once)
    with pytest.raises(RuntimeError):
        weather_service.get_live_forecast(5)
    weather_service.get_live_forecast(5)
    assert failures[0] == 2


def test_empty_forecast_result_is_cached(monkeypatch):
    weather_service.clear_forecast_cache()
    calls = []
    settings = type("Settings", (), {
        "farm_latitude": 1.0, "farm_longitude": 2.0, "weather_forecast_cache_seconds": 900,
    })()
    monkeypatch.setattr(weather_service, "get_settings", lambda: settings)
    monkeypatch.setattr(weather_service, "_fetch_live_forecast", lambda days: calls.append(days) or [])

    assert weather_service.get_live_forecast(7) == []
    assert weather_service.get_live_forecast(7) == []
    assert calls == [7]


def test_weather_error_response_hides_upstream_details(monkeypatch):
    from app.routers import weather as weather_router

    def fail(_days):
        raise RuntimeError("upstream detail should stay server-side")

    monkeypatch.setattr(weather_router, "get_live_forecast", fail)
    with pytest.raises(HTTPException) as error:
        weather_router.weather_forecast(days=7, _=None)
    assert error.value.status_code == 503
    assert "upstream detail" not in error.value.detail


def test_empty_forecast_cache_ttl_is_bounded(monkeypatch):
    weather_service.clear_forecast_cache()
    settings = type("Settings", (), {
        "farm_latitude": 1.0, "farm_longitude": 2.0,
        "weather_forecast_cache_seconds": 900,
        "weather_forecast_empty_cache_seconds": 90,
    })()
    monkeypatch.setattr(weather_service, "get_settings", lambda: settings)
    monkeypatch.setattr(weather_service, "time", type("Clock", (), {"monotonic": staticmethod(lambda: 100.0)})())
    monkeypatch.setattr(weather_service, "_fetch_live_forecast", lambda _days: [])

    assert weather_service.get_live_forecast(7) == []
    expires_at = next(iter(weather_service._FORECAST_CACHE.values()))[0]
    assert 0 <= expires_at - 100.0 <= 60


def test_ui_and_scheduled_weather_timeouts_are_separate(monkeypatch):
    from app import main
    from app.routers import weather as weather_router

    settings = type("Settings", (), {
        "farm_latitude": 1.0, "farm_longitude": 2.0,
        "farm_timezone": "UTC", "weather_request_timeout_seconds": 3.0,
        "weather_job_timeout_seconds": 15.0, "weather_forecast_cache_seconds": 0,
        "weather_forecast_empty_cache_seconds": 30,
    })()
    monkeypatch.setattr(weather_service, "get_settings", lambda: settings)
    monkeypatch.setattr(weather_router, "get_settings", lambda: settings)
    payload = {
        "daily": {"time": [], "temperature_2m_max": [], "temperature_2m_min": [],
                  "precipitation_sum": [], "precipitation_probability_max": [], "weather_code": []},
        "hourly": {"time": [], "relative_humidity_2m": []},
    }
    weather_service.clear_forecast_cache()
    with patch("app.services.weather.httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.json.return_value = payload
        mock_resp.raise_for_status.return_value = None
        mock_client.get.return_value = mock_resp
        mock_client.__enter__.return_value = mock_client
        mock_client_cls.return_value = mock_client
        weather_router.weather_forecast(days=7, _=None)
        assert mock_client_cls.call_args.kwargs["timeout"] == 3.0

        weather_service.clear_forecast_cache()
        weather_service.get_live_forecast(7)
        assert mock_client_cls.call_args.kwargs["timeout"] == 15.0

    observed = []
    monkeypatch.setattr(weather_router, "sync_yesterday_weather", lambda _db: observed.append(
        weather_service._weather_timeout("weather_job_timeout_seconds", 15.0)
    ))
    weather_router.sync_weather(db=object(), _=None)
    assert observed == [3.0]

    class SessionContext:
        def __enter__(self):
            return object()

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(main, "get_settings", lambda: settings)
    monkeypatch.setattr(main, "SessionLocal", SessionContext)
    scheduled_timeouts = []
    main._run_scheduled_job("sync", lambda _db: scheduled_timeouts.append(
        weather_service._weather_timeout("weather_job_timeout_seconds", 15.0)
    ))
    monkeypatch.setattr(main, "catch_up_weather_history", lambda _db: scheduled_timeouts.append(
        weather_service._weather_timeout("weather_job_timeout_seconds", 15.0)
    ))
    main.run_weather_history_catchup_job()
    assert scheduled_timeouts == [15.0, 15.0]
