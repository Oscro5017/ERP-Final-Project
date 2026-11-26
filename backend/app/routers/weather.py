from datetime import date
import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import WeatherLog
from ..schemas import WeatherForecastDay, WeatherLogResponse, WeatherSyncResponse
from ..security import get_current_user
from ..services.weather import get_live_forecast, sync_yesterday_weather, weather_timeout_override
from ..config import get_settings

router = APIRouter(prefix="/weather", tags=["weather"])
logger = logging.getLogger(__name__)


@router.get("/forecast", response_model=list[WeatherForecastDay])
def weather_forecast(
    days: int = Query(7, ge=5, le=14),
    _=Depends(get_current_user),
):
    try:
        with weather_timeout_override(get_settings().weather_request_timeout_seconds):
            return get_live_forecast(days=days)
    except Exception:
        logger.exception("Weather forecast request failed.")
        raise HTTPException(
            status_code=503,
            detail="ไม่สามารถดึงข้อมูลพยากรณ์อากาศได้ในขณะนี้",
        )


@router.get("/history", response_model=list[WeatherLogResponse])
def weather_history(
    from_date: date | None = Query(None, alias="from"),
    to_date: date | None = Query(None, alias="to"),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    query = select(WeatherLog).order_by(WeatherLog.log_date.desc())
    if from_date:
        query = query.where(WeatherLog.log_date >= from_date)
    if to_date:
        query = query.where(WeatherLog.log_date <= to_date)

    return db.scalars(query).all()


@router.post("/sync-yesterday", response_model=WeatherSyncResponse)
def sync_weather(
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    try:
        with weather_timeout_override(get_settings().weather_request_timeout_seconds):
            log = sync_yesterday_weather(db)
        if log is None:
            return WeatherSyncResponse(
                message="ต้นทางยังไม่มีข้อมูลสภาพอากาศที่ครบถ้วน จึงยังไม่ได้บันทึก",
                log=None,
            )
        return WeatherSyncResponse(
            message="บันทึกข้อมูลสภาพอากาศของเมื่อวานสำเร็จ",
            log=log,
        )
    except Exception:
        logger.exception("Weather history sync request failed.")
        raise HTTPException(
            status_code=500,
            detail="เกิดข้อผิดพลาดในการบันทึกข้อมูลสภาพอากาศ",
        )
