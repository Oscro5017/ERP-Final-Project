import logging
import math
import threading
import time
from copy import deepcopy
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import ForecastSnapshot, WeatherLog

OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
logger = logging.getLogger(__name__)
_FORECAST_CACHE: dict[tuple[float, float, int], tuple[float, list[dict]]] = {}
_FORECAST_CACHE_LOCK = threading.Lock()
_WEATHER_TIMEOUT_OVERRIDE: ContextVar[float | None] = ContextVar("weather_timeout_override", default=None)


@contextmanager
def weather_timeout_override(seconds: float):
    token = _WEATHER_TIMEOUT_OVERRIDE.set(seconds)
    try:
        yield
    finally:
        _WEATHER_TIMEOUT_OVERRIDE.reset(token)


def _weather_timeout(setting_name: str, fallback: float) -> float:
    override = _WEATHER_TIMEOUT_OVERRIDE.get()
    if override is not None:
        return override
    return float(getattr(get_settings(), setting_name, fallback))

WMO_WEATHER_CODES: dict[int, str] = {
    0: "ท้องฟ้าแจ่มใส",
    1: "ท้องฟ้าโปร่งเป็นส่วนใหญ่",
    2: "มีเมฆบางส่วน",
    3: "มีเมฆมาก",
    45: "มีหมอก",
    48: "มีหมอกจัด",
    51: "ฝนตกปรอยๆ เล็กน้อย",
    53: "ฝนตกปรอยๆ ปานกลาง",
    55: "ฝนตกปรอยๆ หนาแน่น",
    56: "ฝนละอองเยือกแข็ง",
    57: "ฝนละอองเยือกแข็งหนาแน่น",
    61: "ฝนตกเล็กน้อย",
    63: "ฝนตกปานกลาง",
    65: "ฝนตกหนัก",
    66: "ฝนเยือกแข็งเล็กน้อย",
    67: "ฝนเยือกแข็งหนัก",
    71: "หิมะตกเล็กน้อย",
    73: "หิมะตกปานกลาง",
    75: "หิมะตกหนัก",
    77: "เกล็ดหิมะ",
    80: "ฝนซู่เล็กน้อย",
    81: "ฝนซู่ปานกลาง",
    82: "ฝนซู่หนักมาก",
    85: "หิมะตกประปราย",
    86: "หิมะตกหนักประปราย",
    95: "พายุฝนฟ้าคะนอง",
    96: "พายุฝนฟ้าคะนองพร้อมลูกเห็บเล็กน้อย",
    99: "พายุฝนฟ้าคะนองพร้อมลูกเห็บตกหนัก",
}


def decode_weather_code(code: int) -> str:
    return WMO_WEATHER_CODES.get(code, "สภาพอากาศทั่วไป")


def _fetch_live_forecast(days: int) -> list[dict]:
    settings = get_settings()
    params = {
        "latitude": settings.farm_latitude,
        "longitude": settings.farm_longitude,
        "timezone": settings.farm_timezone,
        "forecast_days": min(max(days, 5), 14),
        "daily": ["weather_code", "temperature_2m_max", "temperature_2m_min", "precipitation_sum", "precipitation_probability_max"],
        "hourly": ["relative_humidity_2m"],
    }
    with httpx.Client(timeout=_weather_timeout("weather_job_timeout_seconds", 15.0)) as client:
        response = client.get(OPEN_METEO_FORECAST_URL, params=params)
        response.raise_for_status()
        data = response.json()

    if not isinstance(data, dict) or not isinstance(data.get("daily"), dict) or not isinstance(data.get("hourly"), dict):
        logger.warning("Open-Meteo forecast response is missing daily/hourly objects; no forecast days accepted.")
        return []

    daily = data["daily"]
    times = daily.get("time", [])
    temp_maxes = daily.get("temperature_2m_max", [])
    temp_mines = daily.get("temperature_2m_min", [])
    precips = daily.get("precipitation_sum", [])
    precip_probabilities = daily.get("precipitation_probability_max", [])
    codes = daily.get("weather_code", [])

    hourly = data.get("hourly", {})
    h_times = hourly.get("time", [])
    h_humidities = hourly.get("relative_humidity_2m", [])

    # Group hourly humidity by date; malformed entries are ignored, not replaced.
    humidity_by_date: dict[str, list[float]] = {}
    if isinstance(h_times, list) and isinstance(h_humidities, list):
        for t, h in zip(h_times, h_humidities):
            try:
                d_str = date.fromisoformat(str(t)[:10]).isoformat()
                numeric_humidity = float(h)
                if math.isfinite(numeric_humidity):
                    humidity_by_date.setdefault(d_str, []).append(numeric_humidity)
            except (TypeError, ValueError):
                continue

    daily_fields = (temp_maxes, temp_mines, precips, precip_probabilities, codes)
    if not isinstance(times, list) or any(not isinstance(field, list) for field in daily_fields):
        logger.warning("Open-Meteo forecast response has incomplete daily arrays; no forecast days accepted.")
        return []

    forecast: list[dict] = []
    for i, t_str in enumerate(times):
        try:
            forecast_date = date.fromisoformat(str(t_str))
            values = [field[i] for field in daily_fields]
            numeric_values = [float(value) for value in values[:4]]
            if any(not math.isfinite(value) for value in numeric_values) or values[4] is None:
                raise ValueError("missing or non-finite daily value")
            w_code = int(values[4])
            h_list = humidity_by_date.get(forecast_date.isoformat(), [])
            if not h_list:
                raise ValueError("missing hourly humidity")
            avg_h = round(sum(h_list) / len(h_list), 1)
        except (IndexError, TypeError, ValueError) as exc:
            logger.warning("Skipping incomplete Open-Meteo forecast day at index %s: %s", i, exc)
            continue

        forecast.append({
            "date": forecast_date,
            "temp_min": numeric_values[1],
            "temp_max": numeric_values[0],
            "humidity": avg_h,
            "rainfall": numeric_values[2],
            "precip_probability": numeric_values[3],
            "condition": decode_weather_code(w_code),
            "weather_code": w_code,
        })

    return forecast


def clear_forecast_cache() -> None:
    with _FORECAST_CACHE_LOCK:
        _FORECAST_CACHE.clear()


def get_live_forecast(days: int = 7) -> list[dict]:
    """Fetch a live forecast with a thread-safe TTL cache; errors are never cached."""
    settings = get_settings()
    requested_days = min(max(days, 5), 14)
    key = (settings.farm_latitude, settings.farm_longitude, requested_days)
    now = time.monotonic()
    with _FORECAST_CACHE_LOCK:
        cached = _FORECAST_CACHE.get(key)
        if cached and cached[0] > now:
            return deepcopy(cached[1])
        if cached:
            _FORECAST_CACHE.pop(key, None)
        result = _fetch_live_forecast(requested_days)
        ttl = max(0, settings.weather_forecast_cache_seconds)
        if not result:
            empty_ttl = max(0, min(60, getattr(settings, "weather_forecast_empty_cache_seconds", 30)))
            ttl = min(ttl, empty_ttl)
        _FORECAST_CACHE[key] = (
            time.monotonic() + ttl,
            deepcopy(result),
        )
        return result


def fetch_and_save_weather_for_date(db: Session, target_date: date) -> WeatherLog | None:
    """
    Fetches actual historical weather for target_date from Open-Meteo and upserts into WeatherLog.
    Guarantees no duplicate row for the same date.
    """
    settings = get_settings()
    date_str = target_date.isoformat()
    params = {
        "latitude": settings.farm_latitude,
        "longitude": settings.farm_longitude,
        "timezone": settings.farm_timezone,
        "start_date": date_str,
        "end_date": date_str,
        "daily": ["weather_code", "temperature_2m_max", "temperature_2m_min", "precipitation_sum"],
        "hourly": ["relative_humidity_2m"],
    }
    with httpx.Client(timeout=_weather_timeout("weather_job_timeout_seconds", 15.0)) as client:
        response = client.get(OPEN_METEO_FORECAST_URL, params=params)
        response.raise_for_status()
        data = response.json()

    daily = data.get("daily") if isinstance(data, dict) else None
    hourly = data.get("hourly") if isinstance(data, dict) else None
    if not isinstance(daily, dict) or not isinstance(hourly, dict):
        logger.warning("Open-Meteo historical response is missing daily/hourly objects for %s; no row written.", target_date)
        return None

    try:
        daily_times = daily.get("time")
        if not isinstance(daily_times, list) or target_date.isoformat() not in daily_times:
            raise ValueError("target date missing")
        index = daily_times.index(target_date.isoformat())
        required = (
            daily.get("temperature_2m_max"), daily.get("temperature_2m_min"),
            daily.get("precipitation_sum"), daily.get("weather_code"),
        )
        if any(not isinstance(field, list) for field in required):
            raise ValueError("invalid daily arrays")
        values = [field[index] for field in required]
        temp_max, temp_min, rainfall = (float(value) for value in values[:3])
        if any(not math.isfinite(value) for value in (temp_max, temp_min, rainfall)) or values[3] is None:
            raise ValueError("missing or non-finite daily value")
        weather_code = int(values[3])
        humidity_values = hourly.get("relative_humidity_2m")
        humidity_times = hourly.get("time")
        if not isinstance(humidity_values, list) or not isinstance(humidity_times, list):
            raise ValueError("missing hourly humidity series")
        humidities = [
            float(value) for timestamp, value in zip(humidity_times, humidity_values)
            if isinstance(timestamp, str) and timestamp.startswith(target_date.isoformat()) and value is not None
        ]
        if not humidities or any(not math.isfinite(value) for value in humidities):
            raise ValueError("missing or invalid hourly humidity")
        humidity = round(sum(humidities) / len(humidities), 1)
    except (IndexError, TypeError, ValueError) as exc:
        logger.warning("Skipping incomplete Open-Meteo historical day %s: %s", target_date, exc)
        return None

    condition = decode_weather_code(weather_code)

    existing = db.scalar(select(WeatherLog).where(WeatherLog.log_date == target_date))
    now = datetime.utcnow()

    if existing:
        existing.temp_min = temp_min
        existing.temp_max = temp_max
        existing.humidity = humidity
        existing.rainfall = rainfall
        existing.condition = condition
        existing.fetched_at = now
        db.commit()
        db.refresh(existing)
        return existing

    new_log = WeatherLog(
        log_date=target_date,
        temp_min=temp_min,
        temp_max=temp_max,
        humidity=humidity,
        rainfall=rainfall,
        condition=condition,
        fetched_at=now,
    )
    db.add(new_log)
    db.commit()
    db.refresh(new_log)
    return new_log


def sync_yesterday_weather(db: Session) -> WeatherLog | None:
    """
    Syncs weather data for yesterday (ran daily by background job).
    """
    yesterday = date.today() - timedelta(days=1)
    return fetch_and_save_weather_for_date(db, yesterday)


def capture_forecast_snapshots(db: Session, issued_at: datetime | None = None) -> list[ForecastSnapshot]:
    settings = get_settings()
    requested_at = issued_at
    forecast = get_live_forecast(days=7)
    issued_at = requested_at or datetime.now(ZoneInfo(settings.farm_timezone))
    issued_date = issued_at.date()
    snapshots = []

    for day in forecast:
        target_date = day["date"]
        snapshot = db.scalar(select(ForecastSnapshot).where(
            ForecastSnapshot.issued_date == issued_date,
            ForecastSnapshot.target_date == target_date,
            ForecastSnapshot.source == "open-meteo",
        ))
        values = {
            "issued_at": issued_at,
            "lead_days": (target_date - issued_date).days,
            "temp_min": day["temp_min"],
            "temp_max": day["temp_max"],
            "humidity": day["humidity"],
            "precip_probability": day["precip_probability"],
            "precip_mm": day["rainfall"],
            "condition": day["condition"],
        }
        if snapshot is None:
            snapshot = ForecastSnapshot(
                issued_date=issued_date,
                target_date=target_date,
                source="open-meteo",
                **values,
            )
            db.add(snapshot)
        else:
            for field, value in values.items():
                setattr(snapshot, field, value)
        snapshots.append(snapshot)

    db.commit()
    for snapshot in snapshots:
        db.refresh(snapshot)
    return snapshots


def ensure_today_forecast_snapshot(db: Session, today: date | None = None) -> list[ForecastSnapshot]:
    settings = get_settings()
    today = today or datetime.now(ZoneInfo(settings.farm_timezone)).date()
    existing_id = db.scalar(
        select(ForecastSnapshot.id)
        .where(ForecastSnapshot.issued_date == today)
        .limit(1)
    )
    if existing_id is not None:
        return []
    return capture_forecast_snapshots(db, issued_at=datetime.now(ZoneInfo(settings.farm_timezone)))


def catch_up_weather_history(db: Session, today: date | None = None) -> int:
    settings = get_settings()
    today = today or datetime.now(ZoneInfo(settings.farm_timezone)).date()
    start_date = today - timedelta(days=14)
    end_date = today - timedelta(days=1)
    existing_dates = set(db.scalars(
        select(WeatherLog.log_date).where(
            WeatherLog.log_date >= start_date,
            WeatherLog.log_date <= end_date,
        )
    ).all())
    synced = 0

    for days_ago in range(14, 0, -1):
        target_date = today - timedelta(days=days_ago)
        if target_date in existing_dates:
            continue
        try:
            saved = fetch_and_save_weather_for_date(db, target_date)
            if saved is None:
                continue
            existing_dates.add(target_date)
            synced += 1
        except Exception as exc:
            db.rollback()
            logger.warning("Weather catch-up skipped %s after fetch failure: %s", target_date, exc)

    return synced
