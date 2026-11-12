import asyncio
import io
import logging
import sqlite3
import sys

import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy import inspect
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import main
from app.config import Settings
from app.database import Base, get_db
from app.migrations import migrate_system_meta
from app.models import Customer, Role, SystemMeta
from app.routers.customers import router as customers_router
from app.services import secure_fields
from app.services.encryption_canary import (
    ENCRYPTION_CANARY_KEY,
    ENCRYPTION_CANARY_PLAINTEXT,
    encryption_canary_status,
    ensure_encryption_canary,
)
from scripts.check_decrypt import check_database

TEST_JWT_SECRET = "j" * 48


def make_settings(key: bytes, *, app_env: str = "development") -> Settings:
    values = {
        "_env_file": None,
        "encryption_key": key.decode("ascii"),
        "app_env": app_env,
    }
    if app_env == "production":
        values["jwt_secret"] = TEST_JWT_SECRET
    return Settings(**values)


def make_engine(path: str = "sqlite://"):
    engine = create_engine(
        path,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    migrate_system_meta(engine)
    return engine


def test_system_meta_migration_and_empty_database_canary_are_idempotent(monkeypatch, tmp_path, caplog):
    engine = make_engine(f"sqlite:///{tmp_path / 'empty.sqlite3'}")
    key = Fernet.generate_key()
    monkeypatch.setattr(secure_fields, "_fernet", lambda: Fernet(key))
    settings = make_settings(key)

    migrate_system_meta(engine)
    migrate_system_meta(engine)
    with Session(engine) as db:
        with caplog.at_level(logging.INFO, logger="app.services.encryption_canary"):
            assert ensure_encryption_canary(db, engine, settings) == "ปกติ"
            assert ensure_encryption_canary(db, engine, settings) == "ปกติ"
        canaries = db.scalars(select(SystemMeta).where(SystemMeta.key == ENCRYPTION_CANARY_KEY)).all()
        assert len(canaries) == 1
        assert secure_fields.decrypt_text(canaries[0].value) == ENCRYPTION_CANARY_PLAINTEXT
        assert key.decode("ascii") not in canaries[0].value
        assert "Encryption canary created" in caplog.text
        assert "Encryption canary verified" in caplog.text
    engine.dispose()


def test_system_meta_migration_creates_only_additive_table_idempotently():
    engine = create_engine("sqlite://")
    migrate_system_meta(engine)
    migrate_system_meta(engine)
    inspector = inspect(engine)
    assert inspector.has_table("system_meta")
    columns = {column["name"] for column in inspector.get_columns("system_meta")}
    assert {"id", "key", "value", "created_at", "updated_at"} <= columns
    indexes = inspector.get_indexes("system_meta")
    assert any(index["unique"] and index["column_names"] == ["key"] for index in indexes)
    engine.dispose()


def test_wrong_key_fails_in_production_and_logs_in_development_without_overwrite(monkeypatch, tmp_path, caplog):
    engine = make_engine(f"sqlite:///{tmp_path / 'wrong-key.sqlite3'}")
    original_key = Fernet.generate_key()
    wrong_key = Fernet.generate_key()
    monkeypatch.setattr(secure_fields, "_fernet", lambda: Fernet(original_key))
    with Session(engine) as db:
        assert ensure_encryption_canary(db, engine, make_settings(original_key)) == "ปกติ"
        original_value = db.scalar(select(SystemMeta.value).where(SystemMeta.key == ENCRYPTION_CANARY_KEY))

    monkeypatch.setattr(secure_fields, "_fernet", lambda: Fernet(wrong_key))
    with Session(engine) as db:
        with caplog.at_level(logging.ERROR, logger="app.services.encryption_canary"):
            assert ensure_encryption_canary(db, engine, make_settings(wrong_key)) == "ไม่ตรง"
        assert db.scalar(select(SystemMeta.value).where(SystemMeta.key == ENCRYPTION_CANARY_KEY)) == original_value
        assert "configured key does not match" in caplog.text
        assert original_key.decode("ascii") not in caplog.text
        assert wrong_key.decode("ascii") not in caplog.text

    with Session(engine) as db:
        with pytest.raises(RuntimeError, match="ENCRYPTION_KEY does not match"):
            ensure_encryption_canary(db, engine, make_settings(wrong_key, app_env="production"))
    engine.dispose()


def test_canary_is_not_created_when_existing_encrypted_data_fails_preflight(monkeypatch, tmp_path, caplog):
    engine = make_engine(f"sqlite:///{tmp_path / 'broken-data.sqlite3'}")
    active_key = Fernet.generate_key()
    other_key = Fernet.generate_key()
    broken_token = Fernet(other_key).encrypt(b"SYNTHETIC-BROKEN-CIPHERTEXT")
    monkeypatch.setattr(secure_fields, "_fernet", lambda: Fernet(active_key))
    with Session(engine) as db:
        db.add(Customer(name_encrypted=broken_token, contact_encrypted=None))
        db.commit()
        with caplog.at_level(logging.ERROR, logger="app.services.encryption_canary"):
            assert ensure_encryption_canary(db, engine, make_settings(active_key)) == "ยังไม่มี"
        assert db.scalar(select(SystemMeta).where(SystemMeta.key == ENCRYPTION_CANARY_KEY)) is None
        assert "1 existing encrypted value(s) failed" in caplog.text
        assert broken_token.decode("ascii") not in caplog.text
        assert "SYNTHETIC-BROKEN-CIPHERTEXT" not in caplog.text

    with Session(engine) as db:
        with pytest.raises(RuntimeError, match="key preflight"):
            ensure_encryption_canary(db, engine, make_settings(active_key, app_env="production"))
    engine.dispose()


def test_decrypt_checker_reports_canary_status_without_values(monkeypatch, tmp_path):
    database_path = tmp_path / "checker.sqlite3"
    engine = make_engine(f"sqlite:///{database_path}")
    key = Fernet.generate_key()
    monkeypatch.setattr(secure_fields, "_fernet", lambda: Fernet(key))
    with Session(engine) as db:
        assert ensure_encryption_canary(db, engine, make_settings(key)) == "ปกติ"

    output = io.StringIO()
    assert check_database(database_path, output, include_canary_status=True) == 0
    assert output.getvalue().splitlines()[0] == "Encryption canary: ปกติ"
    assert ENCRYPTION_CANARY_PLAINTEXT not in output.getvalue()
    assert key.decode("ascii") not in output.getvalue()

    other_key = Fernet.generate_key()
    monkeypatch.setattr(secure_fields, "_fernet", lambda: Fernet(other_key))
    output = io.StringIO()
    assert check_database(database_path, output, include_canary_status=True) == 1
    assert output.getvalue().splitlines()[0] == "Encryption canary: ไม่ตรง"
    assert other_key.decode("ascii") not in output.getvalue()
    engine.dispose()


def test_decrypt_checker_cli_reports_missing_canary_and_summary_before_failures(monkeypatch, tmp_path, capsys):
    database_path = tmp_path / "checker-order.sqlite3"
    key = Fernet.generate_key()
    other_key = Fernet.generate_key()
    monkeypatch.setattr(secure_fields, "_fernet", lambda: Fernet(key))
    with sqlite3.connect(database_path) as connection:
        connection.executescript(
            "CREATE TABLE sample_rows (id INTEGER PRIMARY KEY, payload_encrypted BLOB);"
            "INSERT INTO sample_rows(payload_encrypted) VALUES ('malformed');"
        )

    from scripts import check_decrypt

    monkeypatch.setattr(sys, "argv", ["check_decrypt", str(database_path)])
    assert check_decrypt.main() == 1
    output = capsys.readouterr().out
    assert output.splitlines()[0] == "Encryption canary: ยังไม่มี"
    summary_index = output.index("sample_rows.payload_encrypted:")
    row_index = output.index("rowid=")
    assert summary_index < row_index
    assert "malformed" not in output
    assert key.decode("ascii") not in output
    assert other_key.decode("ascii") not in output


def test_decrypt_checker_prints_column_summary_before_failure_rows(monkeypatch, tmp_path):
    database_path = tmp_path / "summary-order.sqlite3"
    key = Fernet.generate_key()
    other_key = Fernet.generate_key()
    monkeypatch.setattr(secure_fields, "_fernet", lambda: Fernet(key))
    with sqlite3.connect(database_path) as connection:
        connection.execute("CREATE TABLE sample_rows (id INTEGER PRIMARY KEY, payload_encrypted BLOB)")
        connection.execute(
            "INSERT INTO sample_rows(payload_encrypted) VALUES (?)",
            (Fernet(other_key).encrypt(b"SYNTHETIC-ROW-MARKER"),),
        )

    output = io.StringIO()
    failures = check_database(database_path, output, include_canary_status=True)
    report = output.getvalue()
    assert failures == 1
    assert report.index("sample_rows.payload_encrypted:") < report.index("rowid=")
    assert "SYNTHETIC-ROW-MARKER" not in report
    assert other_key.decode("ascii") not in report


def test_production_lifespan_refuses_mismatched_canary(monkeypatch):
    original_key = Fernet.generate_key()
    wrong_key = Fernet.generate_key()
    engine = make_engine()
    sessions = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(secure_fields, "_fernet", lambda: Fernet(original_key))
    with sessions() as db:
        assert ensure_encryption_canary(db, engine, make_settings(original_key)) == "ปกติ"

    monkeypatch.setattr(secure_fields, "_fernet", lambda: Fernet(wrong_key))
    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr(main, "SessionLocal", sessions)
    settings = make_settings(wrong_key, app_env="production")
    api = main.create_app(settings)

    async def start_application():
        async with main.lifespan(api):
            pass

    with pytest.raises(RuntimeError, match="ENCRYPTION_KEY does not match"):
        asyncio.run(start_application())
    engine.dispose()


def test_application_lifespan_creates_canary_before_serving(monkeypatch):
    key = Fernet.generate_key()
    engine = make_engine()
    sessions = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    class Scheduler:
        running = False

        def add_job(self, *_args, **_kwargs):
            pass

        def start(self):
            self.running = True

        def get_jobs(self):
            return []

        def shutdown(self):
            self.running = False

    monkeypatch.setattr(secure_fields, "_fernet", lambda: Fernet(key))
    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr(main, "SessionLocal", sessions)
    monkeypatch.setattr(main, "scheduler", Scheduler())
    monkeypatch.setattr(main, "run_weather_catchup_job", lambda: None)
    api = main.create_app(make_settings(key))

    async def start_and_stop():
        async with main.lifespan(api):
            with sessions() as db:
                assert db.scalar(select(SystemMeta).where(SystemMeta.key == ENCRYPTION_CANARY_KEY)) is not None

    asyncio.run(start_and_stop())
    engine.dispose()


def test_production_lifespan_rejects_mismatched_canary_before_scheduler(monkeypatch, tmp_path):
    original_key = Fernet.generate_key()
    wrong_key = Fernet.generate_key()
    engine = make_engine()
    sessions = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(secure_fields, "_fernet", lambda: Fernet(original_key))
    with sessions() as db:
        ensure_encryption_canary(db, engine, make_settings(original_key))

    class Scheduler:
        running = False

        def add_job(self, *_args, **_kwargs):
            pass

        def start(self):
            self.running = True

        def get_jobs(self):
            return []

        def shutdown(self):
            self.running = False

    monkeypatch.setattr(secure_fields, "_fernet", lambda: Fernet(wrong_key))
    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr(main, "SessionLocal", sessions)
    scheduler = Scheduler()
    monkeypatch.setattr(main, "scheduler", scheduler)
    monkeypatch.setattr(main, "migrate_crop_cycles", lambda _engine: None)
    monkeypatch.setattr(main, "migrate_phase1c", lambda _engine: None)
    monkeypatch.setattr(main, "migrate_customer_contact_encryption", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(main, "migrate_phase1e", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(main, "run_weather_catchup_job", lambda: None)
    settings = Settings(
        _env_file=None,
        encryption_key=wrong_key.decode("ascii"),
        app_env="production",
        jwt_secret=TEST_JWT_SECRET,
        log_dir=str(tmp_path / "logs"),
    )
    api = main.create_app(settings)

    async def start_application():
        async with main.lifespan(api):
            pass

    with pytest.raises(RuntimeError, match="ENCRYPTION_KEY does not match"):
        asyncio.run(start_application())
    assert scheduler.running is False
    engine.dispose()


def test_development_lifespan_logs_mismatch_and_continues(monkeypatch, tmp_path, caplog):
    original_key = Fernet.generate_key()
    wrong_key = Fernet.generate_key()
    engine = make_engine()
    sessions = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(secure_fields, "_fernet", lambda: Fernet(original_key))
    with sessions() as db:
        ensure_encryption_canary(db, engine, make_settings(original_key))
        original_value = db.scalar(select(SystemMeta.value).where(SystemMeta.key == ENCRYPTION_CANARY_KEY))

    class Scheduler:
        running = False

        def add_job(self, *_args, **_kwargs):
            pass

        def start(self):
            self.running = True

        def get_jobs(self):
            return []

        def shutdown(self):
            self.running = False

    scheduler = Scheduler()
    monkeypatch.setattr(secure_fields, "_fernet", lambda: Fernet(wrong_key))
    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr(main, "SessionLocal", sessions)
    monkeypatch.setattr(main, "scheduler", scheduler)
    monkeypatch.setattr(main, "migrate_crop_cycles", lambda _engine: None)
    monkeypatch.setattr(main, "migrate_phase1c", lambda _engine: None)
    monkeypatch.setattr(main, "migrate_customer_contact_encryption", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(main, "migrate_phase1e", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(main, "run_weather_catchup_job", lambda: None)
    settings = Settings(
        _env_file=None,
        encryption_key=wrong_key.decode("ascii"),
        log_dir=str(tmp_path / "logs"),
    )
    api = main.create_app(settings)

    async def start_application():
        async with main.lifespan(api):
            assert scheduler.running is True

    with caplog.at_level(logging.ERROR, logger="app.services.encryption_canary"):
        asyncio.run(start_application())

    assert "configured key does not match" in caplog.text
    assert wrong_key.decode("ascii") not in caplog.text
    with sessions() as db:
        assert db.scalar(select(SystemMeta.value).where(SystemMeta.key == ENCRYPTION_CANARY_KEY)) == original_value
    engine.dispose()


def test_customer_json_key_contract_for_owner_and_developer(monkeypatch):
    engine = make_engine()
    sessions = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    current_role = {"value": Role.owner}
    active_key = Fernet.generate_key()
    other_key = Fernet.generate_key()
    monkeypatch.setattr(secure_fields, "_fernet", lambda: Fernet(active_key))
    with Session(engine) as db:
        db.add_all([
            Customer(
                name_encrypted=secure_fields.encrypt_text("SAFE-OWNER-NAME").encode("ascii"),
                contact_encrypted=secure_fields.encrypt_text("SAFE-CONTACT").encode("ascii"),
            ),
            Customer(
                name_encrypted=Fernet(other_key).encrypt(b"SYNTHETIC-CORRUPT-NAME"),
                contact_encrypted=Fernet(other_key).encrypt(b"SYNTHETIC-CORRUPT-CONTACT"),
            ),
        ])
        db.commit()

    api = FastAPI()

    def override_db():
        with sessions() as db:
            yield db

    api.dependency_overrides[get_db] = override_db
    from app.routers import customers as customer_router_module
    api.dependency_overrides[customer_router_module.get_current_role] = lambda: current_role["value"]
    api.include_router(customers_router)
    client = TestClient(api)
    try:
        owner_rows = client.get("/customers").json()
        original_keys = {"id", "name", "contact", "is_masked"}
        assert set(owner_rows[0]) == original_keys
        assert owner_rows[0]["is_masked"] is False
        assert set(owner_rows[1]) == original_keys | {"decrypt_failed"}
        assert owner_rows[1]["decrypt_failed"] is True

        current_role["value"] = Role.developer
        developer_rows = client.get("/customers").json()
        assert set(developer_rows[0]) == original_keys
        assert set(developer_rows[1]) == original_keys
        assert all(row["is_masked"] is True for row in developer_rows)
        assert all(row["name"].startswith("gAAAA") for row in developer_rows)
    finally:
        client.close()
        api.dependency_overrides.clear()
        engine.dispose()
