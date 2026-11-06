import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from zoneinfo import ZoneInfo
from threading import Event

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import StaticPool

from app.database import configure_sqlite_engine
from app.models import Base, ForecastSnapshot
from app.services import weather as weather_service
from app.migrations import _backup_sqlite_database
from scripts.check_sqlite_foreign_keys import foreign_key_violations


def make_engine(path):
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    configure_sqlite_engine(engine)
    return engine


def test_sqlite_connection_pragmas_and_foreign_keys(tmp_path):
    engine = make_engine(tmp_path / "settings.sqlite3")
    with engine.begin() as connection:
        assert connection.exec_driver_sql("PRAGMA journal_mode").scalar_one().lower() == "wal"
        assert connection.exec_driver_sql("PRAGMA synchronous").scalar_one() == 1
        assert connection.exec_driver_sql("PRAGMA busy_timeout").scalar_one() == 5000
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
        connection.exec_driver_sql("CREATE TABLE parent (id INTEGER PRIMARY KEY)")
        connection.exec_driver_sql("CREATE TABLE child (parent_id INTEGER REFERENCES parent(id))")
    with engine.connect() as connection:
        transaction = connection.begin()
        with pytest.raises(IntegrityError):
            connection.exec_driver_sql("INSERT INTO child(parent_id) VALUES (42)")
        transaction.rollback()
    engine.dispose()


def test_two_sqlite_connections_serialize_writes_with_busy_timeout(tmp_path):
    engine = make_engine(tmp_path / "concurrent.sqlite3")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE samples (value INTEGER NOT NULL)")

    first_has_lock = threading.Event()

    def first_writer():
        with engine.begin() as first:
            first.exec_driver_sql("INSERT INTO samples(value) VALUES (1)")
            first_has_lock.set()
            time.sleep(0.2)

    def second_writer():
        first_has_lock.wait(timeout=2)
        with engine.begin() as second:
            second.exec_driver_sql("INSERT INTO samples(value) VALUES (2)")

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(first_writer)
        second = executor.submit(second_writer)
        first.result(timeout=5)
        second.result(timeout=5)

    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM samples").scalar_one() == 2
    engine.dispose()


def test_backup_api_restore_and_foreign_key_audit_on_copy(tmp_path):
    database_path = tmp_path / "source.sqlite3"
    engine = make_engine(database_path)
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE parent (id INTEGER PRIMARY KEY)")
        connection.exec_driver_sql("CREATE TABLE child (parent_id INTEGER REFERENCES parent(id))")
        connection.exec_driver_sql("INSERT INTO parent(id) VALUES (7)")
        connection.exec_driver_sql("INSERT INTO child(parent_id) VALUES (7)")

    assert foreign_key_violations(database_path, temporary_parent=tmp_path) == {}
    backup_path = _backup_sqlite_database(engine, tmp_path / "backups")
    restored = sqlite3.connect(backup_path)
    try:
        assert restored.execute("SELECT id FROM parent").fetchone() == (7,)
        assert restored.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    finally:
        restored.close()
        engine.dispose()


def test_weather_jobs_are_coalesced_and_have_long_misfire_grace():
    from apscheduler.schedulers.background import BackgroundScheduler

    from app.config import Settings
    from app.main import register_weather_jobs

    scheduler = BackgroundScheduler()
    settings = Settings(encryption_key="MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=")
    register_weather_jobs(scheduler, settings)
    sync_job = scheduler.get_job("weather_daily_sync")
    catchup_job = scheduler.get_job("weather_history_catchup_daily")
    snapshot_job = scheduler.get_job("forecast_snapshot_daily")

    for job in (sync_job, catchup_job, snapshot_job):
        assert job.coalesce is True
        assert job.max_instances == 1
        assert job.misfire_grace_time == settings.scheduler_misfire_grace_seconds

    assert str(catchup_job.trigger.fields[5]) == str(settings.weather_sync_hour)
    assert str(catchup_job.trigger.fields[6]) == "30"


def test_missed_weather_job_runs_within_grace_window():
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.date import DateTrigger
    from datetime import timedelta

    ran = Event()
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        ran.set,
        DateTrigger(run_date=datetime.now() - timedelta(milliseconds=200)),
        id="missed-within-grace",
        coalesce=True,
        max_instances=1,
        misfire_grace_time=2,
    )
    scheduler.start()
    assert ran.wait(timeout=3)
    scheduler.shutdown(wait=True)


def test_startup_snapshot_is_captured_once_for_local_issue_date(tmp_path, monkeypatch):
    engine = create_engine("sqlite://", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    today = datetime.now(ZoneInfo("Asia/Bangkok")).date()
    calls = []
    monkeypatch.setattr(weather_service, "get_settings", lambda: type("S", (), {"farm_timezone": "Asia/Bangkok"})())
    monkeypatch.setattr(weather_service, "capture_forecast_snapshots", lambda db, issued_at=None: calls.append(issued_at) or [])

    from sqlalchemy.orm import Session

    with Session(engine) as db:
        weather_service.ensure_today_forecast_snapshot(db, today=today)
        assert len(calls) == 1
        db.add(ForecastSnapshot(
            issued_at=datetime.now(ZoneInfo("Asia/Bangkok")), issued_date=today,
            target_date=today, lead_days=0, temp_min=1, temp_max=2, humidity=3,
            precip_probability=0, precip_mm=0, condition="clear", source="open-meteo",
        ))
        db.commit()
        weather_service.ensure_today_forecast_snapshot(db, today=today)
        assert len(calls) == 1
    engine.dispose()


def test_foreign_key_audit_reports_orphans_without_printing_row_values(tmp_path):
    database_path = tmp_path / "orphan.sqlite3"
    with sqlite3.connect(database_path) as connection:
        connection.executescript(
            "CREATE TABLE parent (id INTEGER PRIMARY KEY);"
            "CREATE TABLE child (id INTEGER PRIMARY KEY, parent_id INTEGER REFERENCES parent(id));"
            "PRAGMA foreign_keys=OFF;"
            "INSERT INTO child(id, parent_id) VALUES (91, 999);"
        )
    assert foreign_key_violations(database_path, temporary_parent=tmp_path) == {"child": 1}


def test_startup_snapshot_failure_does_not_raise(monkeypatch):
    from app import main

    class SessionContext:
        def __enter__(self):
            return object()

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(main, "SessionLocal", SessionContext)
    monkeypatch.setattr(main, "catch_up_weather_history", lambda _db: 0)
    monkeypatch.setattr(main, "ensure_today_forecast_snapshot", lambda _db: (_ for _ in ()).throw(RuntimeError("upstream down")))
    monkeypatch.setattr(main.time, "sleep", lambda _seconds: None)
    main.run_weather_catchup_job()


def test_scheduler_retries_with_exponential_backoff(monkeypatch):
    from app import main

    class SessionContext:
        def __enter__(self):
            return object()

        def __exit__(self, *_args):
            return False

    attempts = []
    delays = []
    monkeypatch.setattr(main, "SessionLocal", SessionContext)
    monkeypatch.setattr(main.time, "sleep", delays.append)

    def flaky_operation(_db):
        attempts.append(True)
        if len(attempts) < 2:
            raise RuntimeError("transient upstream error")
        return []

    main._run_scheduled_job("test", flaky_operation)
    assert len(attempts) == 2
    assert delays == [1]


def test_scheduled_weather_catchup_retries_once(monkeypatch):
    from app import main

    class SessionContext:
        def __enter__(self):
            return object()

        def __exit__(self, *_args):
            return False

    settings = type("Settings", (), {"weather_job_timeout_seconds": 15.0})()
    attempts = []
    delays = []
    monkeypatch.setattr(main, "get_settings", lambda: settings)
    monkeypatch.setattr(main, "SessionLocal", SessionContext)
    monkeypatch.setattr(main.time, "sleep", delays.append)

    def fail_once(_db):
        attempts.append(True)
        if len(attempts) == 1:
            raise RuntimeError("temporary upstream failure")
        return 0

    monkeypatch.setattr(main, "catch_up_weather_history", fail_once)
    main.run_weather_history_catchup_job()

    assert len(attempts) == 2
    assert delays == [1]
