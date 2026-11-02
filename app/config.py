from functools import lru_cache

from cryptography.fernet import Fernet
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./erp.db"
    jwt_secret: str = "change-this-in-production"
    jwt_expire_minutes: int = 480
    encryption_key: str = ""
    device_token: str | None = None
    cors_origins: str = "http://localhost:8000"
    farm_latitude: float = 18.8072866
    farm_longitude: float = 99.0930437
    farm_timezone: str = "Asia/Bangkok"
    weather_sync_hour: int = 8

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @model_validator(mode="after")
    def validate_encryption_key(self):
        if not self.encryption_key:
            raise ValueError("ENCRYPTION_KEY is required; generate a Fernet key before starting the backend.")
        try:
            Fernet(self.encryption_key.encode("ascii"))
        except (ValueError, UnicodeEncodeError) as exc:
            raise ValueError("ENCRYPTION_KEY must be a valid Fernet key; backend startup has been stopped.") from exc
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
