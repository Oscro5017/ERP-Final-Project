import sqlite3
from datetime import datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import URL

import app.migrations as migrations
from app.services.secure_fields import decrypt_number, decrypt_text, normalize_catalog_name


def build_legacy_database(path):
    connection = sqlite3.connect(path)
    connection.executescript("""
        CREATE TABLE crop_cycles (id INTEGER PRIMARY KEY);
        INSERT INTO crop_cycles (id) VALUES (1);
        CREATE TABLE input_applications (
            id INTEGER PRIMARY KEY, cycle_id INTEGER NOT NULL, applied_date DATE NOT NULL,
            category VARCHAR(80) NOT NULL, note VARCHAR(500), created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL, deleted_at DATETIME
        );
        CREATE TABLE input_items (
            id INTEGER PRIMARY KEY, application_id INTEGER NOT NULL, item_name VARCHAR(140) NOT NULL,
            quantity FLOAT NOT NULL, unit VARCHAR(80) NOT NULL, created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL
        );
        CREATE TABLE input_catalog (
            id INTEGER PRIMARY KEY, item_name VARCHAR(140) NOT NULL, last_unit VARCHAR(80),
            last_category VARCHAR(80), last_used_at DATETIME, use_count INTEGER NOT NULL
        );
        CREATE TABLE tasks (
            id INTEGER PRIMARY KEY, cycle_id INTEGER, title VARCHAR(200) NOT NULL, due_date DATE NOT NULL,
            status VARCHAR(20) NOT NULL, source VARCHAR(20) NOT NULL, created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL, deleted_at DATETIME
        );
    """)
    timestamp = datetime(2026, 10, 1, 8).isoformat(" ")
    connection.execute(
        "INSERT INTO input_applications VALUES (?, ?, ?, ?, ?, ?, ?, NULL)",
        (1, 1, "2026-10-01", "fertilizer", "Private note with MIX-SECRET", timestamp, timestamp),
    )
    connection.execute(
        "INSERT INTO input_items VALUES (?, ?, ?, ?, ?, ?, ?)",
        (1, 1, "MIX-SECRET", 2.75, "ml", timestamp, timestamp),
    )
    connection.executemany(
        "INSERT INTO input_catalog VALUES (?, ?, ?, ?, ?, ?)",
        [
            (1, "CAFÉ", "ml", "fertilizer", "2026-10-01 08:00:00", 2),
            (2, "cafe\u0301", "L", "medicine", "2026-10-02 08:00:00", 3),
        ],
    )
    connection.executemany(
        "INSERT INTO tasks VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)",
        [
            (1, 1, "Private manual task", "2026-10-03", "pending", "manual", timestamp, timestamp),
            (2, 1, "เตรียมเก็บเกี่ยว โต๊ะ 1", "2026-10-03", "pending", "auto", timestamp, timestamp),
        ],
    )
    connection.commit()
    connection.close()


def make_engine(path):
    engine = create_engine(URL.create("sqlite", database=str(path)))
    # Startup renames tasks to activities before the legacy migrations run.
    migrations.migrate_rename_tasks_to_activities(engine)
    return engine


def test_phase1e_migration_encrypts_and_consolidates_legacy_data(tmp_path):
    database_path = tmp_path / "legacy.db"
    backup_dir = tmp_path / "private-backups"
    build_legacy_database(database_path)
    engine = make_engine(database_path)

    result = migrations.migrate_phase1e(engine, backup_dir=backup_dir)

    assert result == {"input_items": 1, "applications": 1, "catalog": 2, "tasks": 1}
    with engine.connect() as connection:
        assert {row[1] for row in connection.exec_driver_sql("PRAGMA table_info(input_items)")} >= {
            "item_name_encrypted", "quantity_encrypted"
        }
        assert "item_name" not in {row[1] for row in connection.exec_driver_sql("PRAGMA table_info(input_items)")}
        assert "quantity" not in {row[1] for row in connection.exec_driver_sql("PRAGMA table_info(input_items)")}
        assert "note" not in {row[1] for row in connection.exec_driver_sql("PRAGMA table_info(input_applications)")}
        item = connection.exec_driver_sql(
            "SELECT item_name_encrypted, quantity_encrypted, unit FROM input_items WHERE id = 1"
        ).one()
        assert decrypt_text(item[0]) == "MIX-SECRET"
        assert decrypt_number(item[1]) == Decimal("2.75")
        assert item[2] == "ml"
        note_token = connection.exec_driver_sql(
            "SELECT note_encrypted FROM input_applications WHERE id = 1"
        ).scalar_one()
        assert decrypt_text(note_token) == "Private note with MIX-SECRET"
        catalog = connection.exec_driver_sql(
            "SELECT name_encrypted, last_unit, last_category, use_count FROM input_catalog"
        ).all()
        assert len(catalog) == 1
        assert normalize_catalog_name(decrypt_text(catalog[0][0])) == "café"
        assert (catalog[0][1], catalog[0][2], catalog[0][3]) == ("L", "medicine", 5)
        manual_task, auto_task = connection.exec_driver_sql(
            "SELECT title, is_encrypted FROM activities ORDER BY id"
        ).all()
        assert decrypt_text(manual_task[0]) == "Private manual task"
        assert manual_task[1] == 1
        assert auto_task == ("เตรียมเก็บเกี่ยว โต๊ะ 1", 0)
        assert connection.exec_driver_sql("PRAGMA integrity_check").scalar_one() == "ok"

    stored_bytes = database_path.read_bytes()
    backup_path = next(backup_dir.glob("erp-pre-phase1e-*.db"))
    with sqlite3.connect(backup_path) as backup_connection:
        old_catalog_names = [row[0].encode("utf-8") for row in backup_connection.execute("SELECT item_name FROM input_catalog")]
    for plaintext in (
        b"MIX-SECRET",
        b"2.75",
        b"Private manual task",
        "Private note with MIX-SECRET".encode(),
        *old_catalog_names,
    ):
        assert plaintext not in stored_bytes
    assert len(list(backup_dir.glob("erp-pre-phase1e-*.db"))) == 1

    assert migrations.migrate_phase1e(engine, backup_dir=backup_dir) == {
        "input_items": 0, "applications": 0, "catalog": 0, "tasks": 0
    }
    assert len(list(backup_dir.glob("erp-pre-phase1e-*.db"))) == 1
    engine.dispose()


def test_phase1e_round_trip_failure_keeps_legacy_plaintext_and_schema(tmp_path, monkeypatch):
    database_path = tmp_path / "legacy-failure.db"
    backup_dir = tmp_path / "private-backups"
    build_legacy_database(database_path)
    engine = make_engine(database_path)
    monkeypatch.setattr(migrations, "decrypt_text", lambda _token: "wrong value")

    with pytest.raises(RuntimeError, match="no plaintext was removed"):
        migrations.migrate_phase1e(engine, backup_dir=backup_dir)

    with engine.connect() as connection:
        columns = {row[1] for row in connection.exec_driver_sql("PRAGMA table_info(input_items)")}
        assert {"item_name", "quantity"} <= columns
        assert connection.exec_driver_sql("SELECT item_name FROM input_items WHERE id = 1").scalar_one() == "MIX-SECRET"
        assert connection.exec_driver_sql("PRAGMA integrity_check").scalar_one() == "ok"
    engine.dispose()


def test_phase1e_requires_backup_dir_before_migration_changes(tmp_path, monkeypatch):
    from app import config

    database_path = tmp_path / "requires-backup.db"
    build_legacy_database(database_path)
    engine = make_engine(database_path)
    monkeypatch.setattr(config, "get_settings", lambda: type("Settings", (), {"backup_dir": None})())

    with pytest.raises(RuntimeError, match="BACKUP_DIR"):
        migrations.migrate_phase1e(engine)
    with engine.connect() as connection:
        columns = {row[1] for row in connection.exec_driver_sql("PRAGMA table_info(input_items)")}
        assert {"item_name", "quantity"} <= columns
    engine.dispose()


def _run_app_startup_with_engine(monkeypatch, engine, settings):
    import asyncio
    from types import SimpleNamespace

    from sqlalchemy.orm import sessionmaker

    from app import config, main

    class Scheduler:
        running = False

        def add_job(self, *_args, **_kwargs):
            pass

        def start(self):
            self.running = True

        def shutdown(self):
            self.running = False

    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr(main, "SessionLocal", sessionmaker(bind=engine))
    monkeypatch.setattr(main, "scheduler", Scheduler())
    monkeypatch.setattr(main, "run_weather_catchup_job", lambda: None)
    monkeypatch.setattr(config, "get_settings", lambda: SimpleNamespace(backup_dir=None))
    application = main.create_app(settings)

    async def start_application():
        async with main.lifespan(application):
            pass

    asyncio.run(start_application())


def test_startup_on_new_database_does_not_require_backup_dir(monkeypatch):
    from cryptography.fernet import Fernet
    from app.config import Settings

    engine = create_engine("sqlite://")
    settings = Settings(_env_file=None, encryption_key=Fernet.generate_key().decode())

    _run_app_startup_with_engine(monkeypatch, engine, settings)

    engine.dispose()


def test_startup_rejects_required_migration_without_backup_dir(monkeypatch):
    from cryptography.fernet import Fernet
    from app.config import Settings

    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE customers (id INTEGER PRIMARY KEY, contact TEXT)")
    settings = Settings(_env_file=None, encryption_key=Fernet.generate_key().decode())

    with pytest.raises(RuntimeError, match="BACKUP_DIR"):
        _run_app_startup_with_engine(monkeypatch, engine, settings)

    with engine.connect() as connection:
        columns = {row[1] for row in connection.exec_driver_sql("PRAGMA table_info(customers)")}
        assert "contact" in columns
        assert "contact_encrypted" not in columns
    engine.dispose()
