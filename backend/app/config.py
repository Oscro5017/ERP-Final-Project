from functools import lru_cache
from pathlib import Path

from cryptography.fernet import Fernet
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# Runtime files (.env, the SQLite database, logs, the built web app) live at the repository root,
# so the backend reads the same files whether it is started from the root or from backend/.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
SQLITE_PREFIX = "sqlite:///"


def _from_root(value: str) -> str:
    path = Path(value).expanduser()
    return str(path if path.is_absolute() else PROJECT_ROOT / path)


class Settings(BaseSettings):
    app_env: str = "development"
    enable_docs: bool | None = None
    database_url: str = "sqlite:///./erp.db"
    jwt_secret: str = "change-this-in-production"
    jwt_expire_minutes: int = 480
    password_hash_iterations: int = Field(default=120_000, ge=100_000)
    encryption_key: str = ""
    device_token: str | None = None
    initial_owner_password: str | None = None
    initial_developer_password: str | None = None
    backup_dir: str | None = None
    cors_origins: str = "http://localhost:8000"
    trusted_proxy_ips: str = ""
    log_level: str = "INFO"
    log_dir: str = "logs"
    frontend_dir: str = "web/dist"
    farm_latitude: float = 18.8072866
    farm_longitude: float = 99.0930437
    farm_timezone: str = "Asia/Bangkok"
    weather_sync_hour: int = 8
    weather_request_timeout_seconds: float = 3.0
    weather_job_timeout_seconds: float = 15.0
    weather_forecast_cache_seconds: int = 900
    weather_forecast_empty_cache_seconds: int = 30
    scheduler_misfire_grace_seconds: int = 21_600

    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / ".env", extra="ignore")

    @field_validator("enable_docs", "device_token", "initial_owner_password", "initial_developer_password", "backup_dir", mode="before")
    @classmethod
    def empty_optional_values_are_unset(cls, value):
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("database_url")
    @classmethod
    def sqlite_path_starts_at_project_root(cls, value: str) -> str:
        if not value.startswith(SQLITE_PREFIX):
            return value
        path = value[len(SQLITE_PREFIX):]
        if not path or path.startswith(":memory:") or Path(path).is_absolute():
            return value
        return SQLITE_PREFIX + Path(_from_root(path)).as_posix()

    @field_validator("log_dir", "frontend_dir")
    @classmethod
    def directory_starts_at_project_root(cls, value: str) -> str:
        return _from_root(value)

    @model_validator(mode="after")
    def validate_encryption_key(self):
        if not self.encryption_key:
            raise ValueError("ENCRYPTION_KEY is required; generate a Fernet key before starting the backend.")
        try:
            Fernet(self.encryption_key.encode("ascii"))
        except (ValueError, UnicodeEncodeError) as exc:
            raise ValueError("ENCRYPTION_KEY must be a valid Fernet key; backend startup has been stopped.") from exc
        return self

    @model_validator(mode="after")
    def validate_production_settings(self):
        if self.app_env.strip().lower() == "production":
            if self.jwt_secret == "change-this-in-production" or len(self.jwt_secret) < 32:
                raise ValueError("JWT_SECRET must be at least 32 characters in production.")
            if self.device_token and len(self.device_token) < 24:
                raise ValueError("DEVICE_TOKEN must be at least 24 characters in production when configured.")
            if "*" in self.cors_origin_list:
                raise ValueError("CORS_ORIGINS cannot contain a wildcard in production.")
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def trusted_proxy_ip_list(self) -> list[str]:
        return [address.strip() for address in self.trusted_proxy_ips.split(",") if address.strip()]

    @property
    def docs_enabled(self) -> bool:
        if self.enable_docs is not None:
            return self.enable_docs
        return self.app_env.strip().lower() != "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
