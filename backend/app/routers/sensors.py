import hmac
import math
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..models import SensorReading
from ..schemas import SensorReadingResponse, SensorReadingsAccepted, SensorReadingsCreate
from ..security import get_current_user

router = APIRouter(prefix="/sensors", tags=["sensors"])

SENSOR_RANGES = {
    "rain_mm": (0.0, 1000.0),
    "temperature_c": (-50.0, 70.0),
    "humidity_pct": (0.0, 100.0),
}


def _utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise HTTPException(status_code=422, detail="recorded_at must include a timezone")
    return value.astimezone(UTC)


@router.post("/readings", response_model=SensorReadingsAccepted)
def receive_sensor_readings(
    payload: SensorReadingsCreate,
    x_device_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    settings = get_settings()
    if not settings.device_token:
        raise HTTPException(status_code=503, detail="Sensor ingestion is not configured")
    if not x_device_token or not hmac.compare_digest(x_device_token.encode(), settings.device_token.encode()):
        raise HTTPException(status_code=401, detail="Invalid device token")

    now = datetime.now(UTC)
    validated = []
    for reading in payload.readings:
        value_range = SENSOR_RANGES.get(reading.sensor_type)
        if value_range is None:
            raise HTTPException(status_code=422, detail="Unsupported sensor_type")
        if not math.isfinite(reading.value) or not value_range[0] <= reading.value <= value_range[1]:
            raise HTTPException(status_code=422, detail="Sensor value is outside the accepted range")
        recorded_at = _utc_datetime(reading.recorded_at)
        if recorded_at > now.replace(microsecond=0) + timedelta(minutes=5):
            raise HTTPException(status_code=422, detail="recorded_at is too far in the future")
        validated.append((reading, recorded_at))

    accepted_count = 0
    updated_count = 0
    for reading, recorded_at in validated:
        existing = db.scalar(select(SensorReading).where(
            SensorReading.device_id == reading.device_id,
            SensorReading.sensor_type == reading.sensor_type,
            SensorReading.recorded_at == recorded_at,
        ))
        if existing:
            existing.value = reading.value
            existing.unit = reading.unit
            existing.received_at = now
            updated_count += 1
        else:
            db.add(SensorReading(
                device_id=reading.device_id,
                sensor_type=reading.sensor_type,
                value=reading.value,
                unit=reading.unit,
                recorded_at=recorded_at,
                received_at=now,
            ))
            db.flush()
            accepted_count += 1

    db.commit()
    return SensorReadingsAccepted(accepted_count=accepted_count, updated_count=updated_count)


@router.get("/readings", response_model=list[SensorReadingResponse])
def list_sensor_readings(
    sensor_type: str | None = Query(None),
    from_date: datetime | None = Query(None, alias="from"),
    to_date: datetime | None = Query(None, alias="to"),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    if sensor_type and sensor_type not in SENSOR_RANGES:
        raise HTTPException(status_code=422, detail="Unsupported sensor_type")
    query = select(SensorReading)
    if sensor_type:
        query = query.where(SensorReading.sensor_type == sensor_type)
    if from_date:
        query = query.where(SensorReading.recorded_at >= _utc_datetime(from_date))
    if to_date:
        query = query.where(SensorReading.recorded_at <= _utc_datetime(to_date))
    return db.scalars(query.order_by(SensorReading.recorded_at.desc()).limit(limit)).all()