import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .database import Base, SessionLocal, engine
from .logging_config import configure_logging
from .migrations import migrate_crop_cycles, migrate_customer_contact_encryption, migrate_phase1c, migrate_phase1e, migrate_system_meta
from .routers import auth, crop_cycles, customers, input_applications, reference, sensors, tasks, weather
from .seed import seed_database, validate_production_default_passwords
from .services.encryption_canary import ensure_encryption_canary
from .services.weather import (
    capture_forecast_snapshots,
    catch_up_weather_history,
    ensure_today_forecast_snapshot,
    sync_yesterday_weather,
    weather_timeout_override,
)

logger = logging.getLogger("erp.scheduler")
scheduler = AsyncIOScheduler()


def run_weather_sync_job():
    _run_scheduled_job("weather sync", sync_yesterday_weather)


def run_forecast_snapshot_job():
    _run_scheduled_job("forecast snapshot", capture_forecast_snapshots)


def _run_scheduled_job(label, operation):
    max_attempts = 2
    for attempt in range(max_attempts):
        try:
            with weather_timeout_override(get_settings().weather_job_timeout_seconds):
                with SessionLocal() as db:
                    result = operation(db)
            count = len(result) if isinstance(result, list) else result if isinstance(result, int) else int(result is not None)
            logger.info("Scheduled %s completed; processed %s records.", label, count)
            return result
        except Exception:
            if attempt < max_attempts - 1:
                delay = 2 ** attempt
                logger.exception(
                    "Scheduled %s failed on attempt %s/%s; retrying in %s seconds.",
                    label,
                    attempt + 1,
                    max_attempts,
                    delay,
                )
                time.sleep(delay)
            else:
                logger.exception("Scheduled %s failed after %s attempts.", label, max_attempts)


def run_weather_history_catchup_job():
    _run_scheduled_job("weather catch-up", catch_up_weather_history)


def run_weather_catchup_job():
    run_weather_history_catchup_job()

    try:
        result = _run_scheduled_job("startup forecast snapshot", ensure_today_forecast_snapshot)
        if result == []:
            logger.info("Startup forecast snapshot already exists for today.")
        elif result is not None:
            logger.info("Startup forecast snapshot captured %s rows.", len(result))
    except Exception:
        logger.exception("Startup forecast snapshot failed; startup will continue.")


def register_weather_jobs(target_scheduler, settings) -> None:
    shared_options = {
        "replace_existing": True,
        "coalesce": True,
        "max_instances": 1,
        "misfire_grace_time": settings.scheduler_misfire_grace_seconds,
    }
    target_scheduler.add_job(
        run_weather_sync_job,
        CronTrigger(hour=settings.weather_sync_hour, minute=0, timezone=settings.farm_timezone),
        id="weather_daily_sync",
        **shared_options,
    )
    target_scheduler.add_job(
        run_weather_history_catchup_job,
        CronTrigger(hour=settings.weather_sync_hour, minute=30, timezone=settings.farm_timezone),
        id="weather_history_catchup_daily",
        **shared_options,
    )
    target_scheduler.add_job(
        run_forecast_snapshot_job,
        CronTrigger(hour=settings.weather_sync_hour, minute=5, timezone=settings.farm_timezone),
        id="forecast_snapshot_daily",
        **shared_options,
    )


def log_registered_weather_jobs(target_scheduler) -> None:
    for job in target_scheduler.get_jobs():
        logger.info("Registered scheduled job %s; next run at %s.", job.id, job.next_run_time)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = _app.state.settings
    with SessionLocal() as db:
        validate_production_default_passwords(db, settings)

    migrate_system_meta(engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        ensure_encryption_canary(db, engine, settings)

    migrate_crop_cycles(engine)
    migrate_phase1c(engine)
    migrate_customer_contact_encryption(engine, backup_dir=settings.backup_dir)
    migrate_phase1e(engine, backup_dir=settings.backup_dir)
    with SessionLocal() as db:
        seed_database(db, settings=settings)

    worker_count = os.getenv("WEB_CONCURRENCY")
    if worker_count and worker_count.isdigit() and int(worker_count) > 1:
        logger.warning("WEB_CONCURRENCY=%s detected; scheduler runs once per worker. Use one worker only.", worker_count)
    catchup_task = asyncio.create_task(asyncio.to_thread(run_weather_catchup_job))
    try:
        register_weather_jobs(scheduler, settings)
        scheduler.start()
        log_registered_weather_jobs(scheduler)
    except Exception as exc:
        logger.error("Failed to start scheduler: %s", exc)

    yield

    if scheduler.running:
        scheduler.shutdown()
    if not catchup_task.done():
        catchup_task.cancel()


def create_app(settings=None) -> FastAPI:
    app_settings = settings or get_settings()
    configure_logging(app_settings)
    docs_url = "/docs" if app_settings.docs_enabled else None
    redoc_url = "/redoc" if app_settings.docs_enabled else None
    openapi_url = "/openapi.json" if app_settings.docs_enabled else None
    api = FastAPI(
        title="Organic Farm ERP API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=docs_url,
        redoc_url=redoc_url,
        openapi_url=openapi_url,
    )
    api.state.settings = app_settings

    @api.exception_handler(RequestValidationError)
    async def sanitized_validation_error_handler(_request, exc: RequestValidationError):
        errors = [
            {key: value for key, value in error.items() if key not in {"input", "ctx"}}
            for error in exc.errors()
        ]
        return JSONResponse(status_code=422, content={"detail": errors})

    api.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    api.include_router(auth.router)
    api.include_router(reference.router)
    api.include_router(crop_cycles.router)
    api.include_router(customers.router)
    api.include_router(input_applications.router)
    api.include_router(tasks.router)
    api.include_router(weather.router)
    api.include_router(sensors.router)
    api.mount("/assets", StaticFiles(directory="frontend/assets"), name="assets")

    @api.get("/{path:path}", include_in_schema=False)
    def spa_fallback(path: str):
        if path.rstrip("/") == "weather":
            return FileResponse("frontend/index.html")
        if path.startswith(("auth", "crop-cycles", "customers", "tables", "batches", "crop-types", "tasks", "weather", "sensors", "input-applications", "input-catalog")):
            raise HTTPException(status_code=404, detail="Not Found")
        if "." in path.rsplit("/", 1)[-1]:
            raise HTTPException(status_code=404, detail="Not Found")
        return FileResponse("frontend/index.html")

    api.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
    return api


settings = get_settings()
app = create_app(settings)
