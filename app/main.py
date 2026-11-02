import asyncio
import logging
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
from .migrations import migrate_crop_cycles, migrate_customer_contact_encryption, migrate_phase1c, migrate_phase1e
from .routers import auth, crop_cycles, customers, input_applications, reference, sensors, tasks, weather
from .seed import seed_database
from .services.weather import capture_forecast_snapshots, catch_up_weather_history, sync_yesterday_weather

logger = logging.getLogger("erp.scheduler")
scheduler = AsyncIOScheduler()


def run_weather_sync_job():
    logger.info("Running scheduled yesterday weather sync...")
    try:
        with SessionLocal() as db:
            sync_yesterday_weather(db)
        logger.info("Scheduled yesterday weather sync completed successfully.")
    except Exception as exc:
        logger.error("Error in scheduled weather sync: %s", exc)


def run_forecast_snapshot_job():
    logger.info("Capturing scheduled forecast snapshot...")
    try:
        with SessionLocal() as db:
            snapshots = capture_forecast_snapshots(db)
        logger.info("Captured %s forecast snapshot rows.", len(snapshots))
    except Exception as exc:
        logger.error("Forecast snapshot job failed and will be retried on its next schedule: %s", exc)


def run_weather_catchup_job():
    try:
        with SessionLocal() as db:
            synced = catch_up_weather_history(db)
        logger.info("Weather catch-up completed; filled %s missing days.", synced)
    except Exception as exc:
        logger.error("Weather catch-up failed without blocking startup: %s", exc)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    migrate_crop_cycles(engine)
    migrate_phase1c(engine)
    migrate_customer_contact_encryption(engine)
    migrate_phase1e(engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_database(db)

    settings = get_settings()
    catchup_task = asyncio.create_task(asyncio.to_thread(run_weather_catchup_job))
    try:
        scheduler.add_job(
            run_weather_sync_job,
            CronTrigger(hour=settings.weather_sync_hour, minute=0, timezone=settings.farm_timezone),
            id="weather_daily_sync",
            replace_existing=True,
        )
        scheduler.add_job(
            run_forecast_snapshot_job,
            CronTrigger(hour=settings.weather_sync_hour, minute=5, timezone=settings.farm_timezone),
            id="forecast_snapshot_daily",
            replace_existing=True,
        )
        scheduler.start()
    except Exception as exc:
        logger.error("Failed to start scheduler: %s", exc)

    yield

    if scheduler.running:
        scheduler.shutdown()
    if not catchup_task.done():
        catchup_task.cancel()


settings = get_settings()
app = FastAPI(title="Organic Farm ERP API", version="0.1.0", lifespan=lifespan)


@app.exception_handler(RequestValidationError)
async def sanitized_validation_error_handler(_request, exc: RequestValidationError):
    errors = [
        {key: value for key, value in error.items() if key not in {"input", "ctx"}}
        for error in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": errors})


app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origin_list, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(auth.router)
app.include_router(reference.router)
app.include_router(crop_cycles.router)
app.include_router(customers.router)
app.include_router(input_applications.router)
app.include_router(tasks.router)
app.include_router(weather.router)
app.include_router(sensors.router)
app.mount("/assets", StaticFiles(directory="frontend/assets"), name="assets")

@app.get("/{path:path}", include_in_schema=False)
def spa_fallback(path: str):
    if path.startswith(("auth", "crop-cycles", "customers", "tables", "batches", "crop-types", "tasks", "weather", "sensors", "input-applications", "input-catalog")):
        raise HTTPException(status_code=404, detail="Not Found")
    if "." in path.rsplit("/", 1)[-1]:
        raise HTTPException(status_code=404, detail="Not Found")
    return FileResponse("frontend/index.html")

app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")

