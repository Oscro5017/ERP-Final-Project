from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import WeatherLog
from ..schemas import WeatherForecastDay, WeatherLogResponse, WeatherSyncResponse
from ..security import get_current_user
from ..services.weather import fetch_and_save_weather_for_date, get_live_forecast, sync_yesterday_weather

router = APIRouter(prefix="/weather", tags=["weather"])


@router.get("/forecast", response_model=list[WeatherForecastDay])
def weather_forecast(
    days: int = Query(7, ge=5, le=14),
    _=Depends(get_current_user),
):
    try:
        return get_live_forecast(days=days)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"ไม่สามารถเชื่อมต่อบริการสภาพอากาศได้: {str(exc)}",
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
        log = sync_yesterday_weather(db)
        return WeatherSyncResponse(
            message="บันทึกข้อมูลสภาพอากาศของเมื่อวานสำเร็จ",
            log=log,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"เกิดข้อผิดพลาดในการดึงข้อมูลสภาพอากาศ: {str(exc)}",
        )
