import logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import ForecastSnapshot, WeatherLog

OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
logger = logging.getLogger(__name__)

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


def get_live_forecast(days: int = 7) -> list[dict]:
    """
    Fetches live 5-7 days forecast from Open-Meteo without saving to DB.
    """
    settings = get_settings()
    params = {
        "latitude": settings.farm_latitude,
        "longitude": settings.farm_longitude,
        "timezone": settings.farm_timezone,
        "forecast_days": min(max(days, 5), 14),
        "daily": ["weather_code", "temperature_2m_max", "temperature_2m_min", "precipitation_sum", "precipitation_probability_max"],
        "hourly": ["relative_humidity_2m"],
    }
    with httpx.Client(timeout=10.0) as client:
        response = client.get(OPEN_METEO_FORECAST_URL, params=params)
        response.raise_for_status()
        data = response.json()

    daily = data.get("daily", {})
    times = daily.get("time", [])
    temp_maxes = daily.get("temperature_2m_max", [])
    temp_mines = daily.get("temperature_2m_min", [])
    precips = daily.get("precipitation_sum", [])
    precip_probabilities = daily.get("precipitation_probability_max", [])
    codes = daily.get("weather_code", [])

    hourly = data.get("hourly", {})
    h_times = hourly.get("time", [])
    h_humidities = hourly.get("relative_humidity_2m", [])

    # Group hourly humidity by date
    humidity_by_date: dict[str, list[float]] = {}
    for t, h in zip(h_times, h_humidities):
        d_str = t[:10]
        if h is not None:
            humidity_by_date.setdefault(d_str, []).append(float(h))

    forecast: list[dict] = []
    for i, t_str in enumerate(times):
        h_list = humidity_by_date.get(t_str, [])
        avg_h = round(sum(h_list) / len(h_list), 1) if h_list else 75.0
        w_code = int(codes[i]) if i < len(codes) and codes[i] is not None else 0

        forecast.append({
            "date": date.fromisoformat(t_str),
            "temp_min": float(temp_mines[i]) if i < len(temp_mines) and temp_mines[i] is not None else 0.0,
            "temp_max": float(temp_maxes[i]) if i < len(temp_maxes) and temp_maxes[i] is not None else 0.0,
            "humidity": avg_h,
            "rainfall": float(precips[i]) if i < len(precips) and precips[i] is not None else 0.0,
            "precip_probability": float(precip_probabilities[i]) if i < len(precip_probabilities) and precip_probabilities[i] is not None else 0.0,
            "condition": decode_weather_code(w_code),
            "weather_code": w_code,
        })

    return forecast


def fetch_and_save_weather_for_date(db: Session, target_date: date) -> WeatherLog:
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
    with httpx.Client(timeout=10.0) as client:
        response = client.get(OPEN_METEO_FORECAST_URL, params=params)
        response.raise_for_status()
        data = response.json()

    daily = data.get("daily", {})
    temp_max = float(daily.get("temperature_2m_max", [0.0])[0] or 0.0)
    temp_min = float(daily.get("temperature_2m_min", [0.0])[0] or 0.0)
    rainfall = float(daily.get("precipitation_sum", [0.0])[0] or 0.0)
    weather_code = int(daily.get("weather_code", [0])[0] or 0)
    condition = decode_weather_code(weather_code)

    hourly = data.get("hourly", {})
    humidities = [float(h) for h in hourly.get("relative_humidity_2m", []) if h is not None]
    humidity = round(sum(humidities) / len(humidities), 1) if humidities else 75.0

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


def sync_yesterday_weather(db: Session) -> WeatherLog:
    """
    Syncs weather data for yesterday (ran daily by background job).
    """
    yesterday = date.today() - timedelta(days=1)
    return fetch_and_save_weather_for_date(db, yesterday)


def capture_forecast_snapshots(db: Session, issued_at: datetime | None = None) -> list[ForecastSnapshot]:
    settings = get_settings()
    issued_at = issued_at or datetime.now(ZoneInfo(settings.farm_timezone))
    issued_date = issued_at.date()
    forecast = get_live_forecast(days=7)
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
            fetch_and_save_weather_for_date(db, target_date)
            existing_dates.add(target_date)
            synced += 1
        except Exception as exc:
            db.rollback()
            logger.warning("Weather catch-up skipped %s after fetch failure: %s", target_date, exc)

    return synced
