"""Weather and sensor readings."""
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class WeatherForecastDay(BaseModel):
    date: date
    temp_min: float
    temp_max: float
    humidity: float
    rainfall: float
    condition: str
    weather_code: int


class WeatherLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    log_date: date
    temp_min: float
    temp_max: float
    humidity: float
    rainfall: float
    condition: str
    fetched_at: datetime
    source: str = "open-meteo-model"


class WeatherSyncResponse(BaseModel):
    message: str
    log: WeatherLogResponse | None = None


class SensorReadingInput(BaseModel):
    device_id: str = Field(min_length=1, max_length=100)
    sensor_type: str = Field(min_length=1, max_length=40)
    value: float
    unit: str = Field(min_length=1, max_length=20)
    recorded_at: datetime


class SensorReadingsCreate(BaseModel):
    readings: list[SensorReadingInput] = Field(min_length=1, max_length=1000)


class SensorReadingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    device_id: str
    sensor_type: str
    value: float
    unit: str
    recorded_at: datetime
    received_at: datetime


class SensorReadingsAccepted(BaseModel):
    accepted_count: int
    updated_count: int
