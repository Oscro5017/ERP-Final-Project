import logging
from decimal import Decimal
from datetime import date
from types import SimpleNamespace

from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models import (
    Batch,
    CropCycle,
    CropType,
    Customer,
    InputApplication,
    InputCatalog,
    InputItem,
    Role,
    Table,
    Task,
)
from app.routers import customers, input_applications, tasks
from app.services import secure_fields


def test_safe_decryption_returns_failure_values_and_logs_no_token(monkeypatch, caplog):
    key = Fernet.generate_key()
    wrong_key = Fernet.generate_key()
    monkeypatch.setattr(secure_fields, "_fernet", lambda: Fernet(key))
    token = Fernet(wrong_key).encrypt(b"PRIVATE-PLAINTEXT-MARKER").decode("ascii")

    with caplog.at_level(logging.ERROR, logger="app.services.secure_fields"):
        text_result = secure_fields.safe_decrypt_text(
            token, table="tasks", row_id=41, field="title"
        )
        number_result = secure_fields.safe_decrypt_number(
            token, table="input_items", row_id=42, field="quantity"
        )

    assert text_result.value == secure_fields.DECRYPT_FAILED_TEXT
    assert text_result.decrypt_failed is True
    assert number_result.value is None
    assert number_result.decrypt_failed is True
    error_records = [record for record in caplog.records if record.name == "app.services.secure_fields"]
    assert any(record.table == "tasks" and record.row_id == 41 and record.error_type == "InvalidToken" for record in error_records)
    assert any(record.table == "input_items" and record.row_id == 42 for record in error_records)
    assert "table=tasks" in caplog.text
    assert "row_id=41" in caplog.text
    assert "error_type=InvalidToken" in caplog.text
    assert token not in caplog.text
    assert "PRIVATE-PLAINTEXT-MARKER" not in caplog.text


def test_safe_decryption_preserves_valid_values_and_developer_masking(monkeypatch):
    key = Fernet.generate_key()
    monkeypatch.setattr(secure_fields, "_fernet", lambda: Fernet(key))
    text_token = secure_fields.encrypt_text("safe value")
    number_token = secure_fields.encrypt_number(Decimal("12.50"))

    text_result = secure_fields.present_text_safe(
        text_token, Role.owner, table="customers", row_id=1, field="name"
    )
    number_result = secure_fields.present_number_safe(
        number_token, Role.owner, table="input_items", row_id=2, field="quantity"
    )
    developer_result = secure_fields.present_text_safe(
        "not-a-token", Role.developer, table="tasks", row_id=3, field="title"
    )

    assert text_result.value == "safe value"
    assert text_result.decrypt_failed is False
    assert number_result.value == Decimal("12.50")
    assert number_result.decrypt_failed is False
    assert developer_result.value == "not-a-token"
    assert developer_result.decrypt_failed is False


def test_decrypt_failure_logging_is_rate_limited(monkeypatch, caplog):
    monkeypatch.setattr(secure_fields, "_fernet", lambda: Fernet(Fernet.generate_key()))
    secure_fields._DECRYPT_LOG_CACHE.clear()

    with caplog.at_level(logging.ERROR, logger="app.services.secure_fields"):
        for _ in range(3):
            secure_fields.safe_decrypt_text(
                "invalid-token", table="tasks", row_id=99, field="title"
            )

    assert caplog.text.count("Encrypted field decryption failed") == 1


def test_logging_configuration_is_idempotent_and_writes_rotating_log(tmp_path, caplog):
    import logging

    from app.config import Settings
    from app.logging_config import configure_logging

    settings = Settings(
        _env_file=None,
        encryption_key=Fernet.generate_key().decode("ascii"),
        log_level="INFO",
        log_dir=str(tmp_path),
    )
    configure_logging(settings)
    root_logger = logging.getLogger()
    managed_handlers = [
        handler for handler in root_logger.handlers
        if getattr(handler, "_erp_managed_handler", False)
    ]
    assert len(managed_handlers) == 2
    file_handler = next(handler for handler in managed_handlers if hasattr(handler, "maxBytes"))
    assert file_handler.maxBytes == 1_000_000
    assert file_handler.backupCount == 5

    configure_logging(settings)
    assert len([
        handler for handler in root_logger.handlers
        if getattr(handler, "_erp_managed_handler", False)
    ]) == 2

    with caplog.at_level(logging.INFO, logger="erp.test.logging"):
        logging.getLogger("erp.test.logging").info("scheduled log marker")
    assert "scheduled log marker" in (tmp_path / "app.log").read_text(encoding="utf-8")
    assert "scheduled log marker" in caplog.text


def test_registered_scheduler_jobs_log_next_run_times(caplog):
    from apscheduler.schedulers.background import BackgroundScheduler

    from app.config import Settings
    from app.main import log_registered_weather_jobs, register_weather_jobs

    settings = Settings(
        _env_file=None,
        encryption_key=Fernet.generate_key().decode("ascii"),
    )
    scheduler = BackgroundScheduler(timezone="Asia/Bangkok")
    register_weather_jobs(scheduler, settings)
    scheduler.start(paused=True)
    try:
        with caplog.at_level(logging.INFO, logger="erp.scheduler"):
            log_registered_weather_jobs(scheduler)
        for job_id in ("weather_daily_sync", "weather_history_catchup_daily", "forecast_snapshot_daily"):
            assert job_id in caplog.text
        assert "next run at" in caplog.text
    finally:
        scheduler.shutdown(wait=False)


def build_api():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    api = FastAPI()
    api.include_router(tasks.router)
    api.include_router(customers.router)
    api.include_router(input_applications.router)
    current = {"role": Role.owner}

    def override_db():
        with sessions() as db:
            yield db

    api.dependency_overrides[get_db] = override_db
    api.dependency_overrides[tasks.get_current_user] = lambda: SimpleNamespace(role=current["role"])
    api.dependency_overrides[customers.get_current_role] = lambda: current["role"]
    api.dependency_overrides[input_applications.get_current_user] = lambda: SimpleNamespace(role=current["role"])
    return api, engine, sessions, current


def test_corrupt_rows_do_not_break_owner_list_endpoints_or_leak_tokens(monkeypatch, caplog):
    from app.services.secure_fields import encrypt_number, encrypt_text

    api, engine, sessions, current = build_api()
    key = Fernet.generate_key()
    wrong_key = Fernet.generate_key()
    monkeypatch.setattr(secure_fields, "_fernet", lambda: Fernet(key))
    good_name = encrypt_text("SAFE-CUSTOMER")
    good_contact = encrypt_text("SAFE-CONTACT")
    good_task = encrypt_text("SAFE-TASK")
    good_note = encrypt_text("SAFE-NOTE")
    good_item = encrypt_text("SAFE-ITEM")
    good_quantity = encrypt_number(Decimal("2.5"))
    bad_values = {
        "customer_name": Fernet(wrong_key).encrypt(b"PRIVATE-CUSTOMER-MARKER").decode("ascii"),
        "customer_contact": Fernet(wrong_key).encrypt(b"PRIVATE-CONTACT-MARKER").decode("ascii"),
        "task": Fernet(wrong_key).encrypt(b"PRIVATE-TASK-MARKER").decode("ascii"),
        "note": Fernet(wrong_key).encrypt(b"PRIVATE-NOTE-MARKER").decode("ascii"),
        "item": Fernet(wrong_key).encrypt(b"PRIVATE-ITEM-MARKER").decode("ascii"),
        "quantity": Fernet(wrong_key).encrypt(b"private numeric marker").decode("ascii"),
        "catalog": Fernet(wrong_key).encrypt(b"PRIVATE-CATALOG-MARKER").decode("ascii"),
    }
    with sessions() as db:
        db.add_all([
            Customer(name_encrypted=good_name.encode(), contact_encrypted=good_contact.encode()),
            Customer(name_encrypted=bad_values["customer_name"].encode(), contact_encrypted=bad_values["customer_contact"].encode()),
            Task(title=good_task, due_date=date(2026, 11, 6), source="manual", is_encrypted=True),
            Task(title=bad_values["task"], due_date=date(2026, 11, 6), source="manual", is_encrypted=True),
            Table(table_number=1),
            Batch(batch_number=1, start_date=date(2026, 1, 1), week_offset=0),
            CropType(name="Test Crop", nursery_days=1, growth_days=1),
        ])
        db.commit()
        cycle = CropCycle(
            table_id=1, batch_id=1, crop_type_id=1,
            nursery_start=date(2026, 1, 1), status="nursery",
        )
        db.add(cycle)
        db.flush()
        application = InputApplication(
            cycle_id=cycle.id, applied_date=date(2026, 11, 6), category="fertilizer",
            note_encrypted=bad_values["note"].encode(),
        )
        application.items.extend([
            InputItem(item_name_encrypted=good_item.encode(), quantity_encrypted=good_quantity.encode(), unit="kg"),
            InputItem(item_name_encrypted=bad_values["item"].encode(), quantity_encrypted=bad_values["quantity"].encode(), unit="L"),
        ])
        db.add(application)
        db.add_all([
            InputCatalog(name_encrypted=encrypt_text("SAFE-CATALOG").encode(), name_hash="a" * 64, use_count=1),
            InputCatalog(name_encrypted=bad_values["catalog"].encode(), name_hash="b" * 64, use_count=1),
        ])
        db.commit()
        cycle_id = cycle.id
        bad_task_id = db.query(Task).filter(Task.title == bad_values["task"]).one().id

    client = TestClient(api)
    try:
        with caplog.at_level(logging.ERROR, logger="app.services.secure_fields"):
            task_response = client.get("/tasks")
            customer_response = client.get("/customers")
            customer_search = client.get("/customers", params={"q": "safe-customer"})
            application_response = client.get(f"/crop-cycles/{cycle_id}/input-applications")
            catalog_response = client.get("/input-catalog/suggestions", params={"q": "safe"})

        assert task_response.status_code == customer_response.status_code == 200
        task_rows = task_response.json()
        assert [row["title"] for row in task_rows] == ["SAFE-TASK", secure_fields.DECRYPT_FAILED_TEXT]
        assert task_rows[1]["decrypt_failed"] is True

        customers_payload = customer_response.json()
        assert len(customers_payload) == 2
        assert customers_payload[1]["name"] == secure_fields.DECRYPT_FAILED_TEXT
        assert customers_payload[1]["decrypt_failed"] is True
        assert [row["name"] for row in customer_search.json()] == ["SAFE-CUSTOMER"]

        application_row = application_response.json()[0]
        assert application_row["note"] == secure_fields.DECRYPT_FAILED_TEXT
        assert application_row["decrypt_failed"] is True
        assert application_row["items"][0]["item_name"] == "SAFE-ITEM"
        assert application_row["items"][1]["item_name"] == secure_fields.DECRYPT_FAILED_TEXT
        assert application_row["items"][1]["quantity"] is None
        assert application_row["items"][1]["decrypt_failed"] is True

        assert catalog_response.status_code == 200
        assert [item["item_name"] for item in catalog_response.json()["items"]] == ["SAFE-CATALOG"]

        with sessions() as db:
            db_task = db.get(Task, bad_task_id)
            stored_bad_title = db_task.title
        transition = client.patch(f"/tasks/{bad_task_id}", json={"source": "auto"})
        assert transition.status_code == 409
        with sessions() as db:
            assert db.get(Task, bad_task_id).title == stored_bad_title

        current["role"] = Role.developer
        developer_tasks = client.get("/tasks").json()
        developer_customers = client.get("/customers").json()
        assert developer_tasks[1]["title"] == bad_values["task"]
        assert developer_tasks[1]["is_masked"] is True
        assert developer_tasks[1].get("decrypt_failed", False) is False
        assert developer_customers[1]["name"] == bad_values["customer_name"]
        assert developer_customers[1].get("decrypt_failed", False) is False

        log_records = [record for record in caplog.records if record.name == "app.services.secure_fields"]
        logged_text = " ".join(record.getMessage() for record in log_records)
        assert len(log_records) >= 6
        assert all(hasattr(record, "table") and hasattr(record, "row_id") for record in log_records)
        for secret_value in bad_values.values():
            assert secret_value not in logged_text
            assert secret_value not in task_response.text + customer_response.text + application_response.text
        for marker in ("PRIVATE-CUSTOMER-MARKER", "PRIVATE-CONTACT-MARKER", "PRIVATE-TASK-MARKER", "PRIVATE-NOTE-MARKER", "PRIVATE-ITEM-MARKER", "PRIVATE-CATALOG-MARKER"):
            assert marker not in logged_text
            assert marker not in task_response.text + customer_response.text + application_response.text
    finally:
        client.close()
        api.dependency_overrides.clear()
        engine.dispose()