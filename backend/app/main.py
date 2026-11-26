import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.routing import APIRoute
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .database import Base, SessionLocal, engine
from .logging_config import configure_logging
from .migrations import migrate_crop_cycles, migrate_crop_type_product_mapping, migrate_customer_area_encryption, migrate_customer_contact_encryption, migrate_finance_entries, migrate_input_product_mapping, migrate_phase1c, migrate_phase1e, migrate_products_stock, migrate_stock_documents, migrate_system_meta, migrate_task_finance_fields, migrate_unified_insights
from .routers import auth, crop_cycles, customers, dashboard, finance, freshness, input_applications, insights, preferences, products, reference, sales_orders, sensors, stock, suppliers, tasks, trade_documents, weather
from .seed import seed_database, validate_production_default_passwords
from .services.encryption_canary import ensure_encryption_canary
from .services.sales_orders import replan_open_orders_job
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


def run_order_replan_job():
    _run_scheduled_job("order replan", replan_open_orders_job)


def register_order_jobs(target_scheduler, settings) -> None:
    target_scheduler.add_job(
        run_order_replan_job,
        CronTrigger(hour=0, minute=10, timezone=settings.farm_timezone),
        id="order_replan_daily",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=settings.scheduler_misfire_grace_seconds,
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
    migrated_tables = {
        "products", "stock_movements", "suppliers", "stock_documents",
        "stock_document_lines", "finance_entries",
    }
    Base.metadata.create_all(bind=engine, tables=[table for table in Base.metadata.sorted_tables if table.name not in migrated_tables])
    # CropType's new optional mapping points to products; create that additive
    # table before the canary audit reflects foreign-key dependencies.
    migrate_products_stock(engine)
    # Order deliveries reference stock documents, so they must exist for the audit too.
    migrate_stock_documents(engine)
    with SessionLocal() as db:
        ensure_encryption_canary(db, engine, settings)

    migrate_crop_type_product_mapping(engine)
    migrate_input_product_mapping(engine)
    migrate_finance_entries(engine)
    migrate_task_finance_fields(engine)
    migrate_customer_area_encryption(engine)
    migrate_unified_insights(engine)
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
        register_order_jobs(scheduler, settings)
        scheduler.start()
        log_registered_weather_jobs(scheduler)
    except Exception as exc:
        logger.error("Failed to start scheduler: %s", exc)

    yield

    if scheduler.running:
        scheduler.shutdown()
    if not catchup_task.done():
        catchup_task.cancel()


NON_PAGE_SECTIONS = {"assets", "docs", "redoc", "openapi.json"}


def api_path_sections(api: FastAPI) -> set[str]:
    """First path segment of every API endpoint, e.g. "stock" for /stock/movements."""
    return {route.path.strip("/").split("/", 1)[0] for route in api.routes if isinstance(route, APIRoute) and route.include_in_schema} - {""}


def is_page_request(method: str, path: str, accept: str) -> bool:
    if method != "GET" or "text/html" not in accept:
        return False
    first, last = path.strip("/").split("/", 1)[0], path.rsplit("/", 1)[-1]
    return first not in NON_PAGE_SECTIONS and "." not in last


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
    api.include_router(dashboard.router)
    api.include_router(customers.router)
    api.include_router(finance.router)
    api.include_router(freshness.router)
    api.include_router(insights.router)
    api.include_router(input_applications.router)
    api.include_router(preferences.router)
    api.include_router(products.router)
    api.include_router(sales_orders.router)
    api.include_router(suppliers.router)
    api.include_router(stock.router)
    api.include_router(trade_documents.router)
    api.include_router(tasks.router)
    api.include_router(weather.router)
    api.include_router(sensors.router)
    frontend = Path(app_settings.frontend_dir)
    if not (frontend / "index.html").is_file():
        # The API still works before the web app is built; only the pages are missing.
        logger.warning("Web app is not built; run `npm run build` in web/ to serve the pages.")
        return api
    index_page = frontend / "index.html"
    api_sections = api_path_sections(api)
    api.mount("/assets", StaticFiles(directory=frontend / "assets"), name="assets")

    @api.middleware("http")
    async def serve_pages_to_browsers(request: Request, call_next):
        # A browser opening or refreshing a page asks for HTML, even when the page path matches an API
        # path such as /insights. API calls ask for JSON, so they still reach the endpoints.
        if is_page_request(request.method, request.url.path, request.headers.get("accept", "")):
            return FileResponse(index_page)
        return await call_next(request)

    @api.get("/{path:path}", include_in_schema=False)
    def spa_fallback(path: str):
        if path.rstrip("/") == "weather":
            return FileResponse(index_page)
        if path.split("/", 1)[0] in api_sections or "." in path.rsplit("/", 1)[-1]:
            raise HTTPException(status_code=404, detail="Not Found")
        return FileResponse(index_page)

    api.mount("/", StaticFiles(directory=frontend, html=True), name="frontend")
    return api


settings = get_settings()
app = create_app(settings)
