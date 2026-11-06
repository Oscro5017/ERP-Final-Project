from decimal import Decimal

import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.database import Base, get_db
from app import migrations
from app.migrations import migrate_customer_contact_encryption
from app.models import Customer, Role
from app.routers.customers import router as customers_router
from app.services.secure_fields import (
    decrypt_number,
    decrypt_text,
    encrypt_number,
    encrypt_text,
    present_aggregate,
    present_number,
    present_text,
)
from app.security import get_current_role


def test_secure_field_helpers_for_both_roles():
    text_token = encrypt_text("Sample Customer")
    assert decrypt_text(text_token) == "Sample Customer"
    assert text_token.startswith("gAAAA")
    assert present_text(text_token, Role.owner) == "Sample Customer"
    assert present_text(text_token, Role.developer) == text_token

    number_token = encrypt_number(Decimal("1234.50"))
    assert decrypt_number(number_token) == Decimal("1234.50")
    assert present_number(number_token, Role.owner) == Decimal("1234.50")
    assert present_number(number_token, Role.developer) == number_token

    owner_aggregate = present_aggregate(Decimal("1234.50"), Role.owner)
    developer_aggregate = present_aggregate(Decimal("1234.50"), Role.developer)
    assert owner_aggregate == {"value": Decimal("1234.50"), "is_masked": False}
    assert developer_aggregate["is_masked"] is True
    assert isinstance(developer_aggregate["value"], str)
    assert decrypt_text(developer_aggregate["value"]) == "1234.50"


def test_secure_number_helpers_reject_non_finite_values():
    with pytest.raises(ValueError, match="finite decimal"):
        encrypt_number("NaN")
    with pytest.raises(ValueError, match="finite decimal"):
        present_aggregate("Infinity", Role.owner)


def test_encryption_key_must_be_present_and_valid(monkeypatch):
    monkeypatch.delenv("ENCRYPTION_KEY", raising=False)
    with pytest.raises(ValueError, match="ENCRYPTION_KEY is required"):
        Settings(_env_file=None)
    with pytest.raises(ValueError, match="valid Fernet key"):
        Settings(_env_file=None, encryption_key="invalid")
    Settings(_env_file=None, encryption_key=Fernet.generate_key().decode("ascii"))


def test_customer_contact_migration_backups_encrypts_and_removes_plaintext(tmp_path):
    database_path = tmp_path / "farm.db"
    engine = create_engine(f"sqlite:///{database_path}")
    legacy_name = encrypt_text("Dummy Customer")
    with engine.begin() as connection:
        connection.exec_driver_sql("""
            CREATE TABLE customers (
                id INTEGER PRIMARY KEY,
                name_encrypted BLOB NOT NULL,
                contact VARCHAR(160) NOT NULL DEFAULT '',
                created_at TIMESTAMP,
                updated_at TIMESTAMP,
                deleted_at TIMESTAMP
            )
        """)
        connection.execute(
            text("INSERT INTO customers (id, name_encrypted, contact) VALUES (1, :name, :contact)"),
            {"name": legacy_name.encode("ascii"), "contact": "555-0102-DUMMY"},
        )
        connection.execute(text("CREATE INDEX ix_customers_deleted_at ON customers (deleted_at)"))

    backup_dir = tmp_path / "private-backups"
    assert migrate_customer_contact_encryption(engine, backup_dir) == 1
    assert migrate_customer_contact_encryption(engine, backup_dir) == 0

    with engine.connect() as connection:
        columns = {column["name"] for column in inspect(connection).get_columns("customers")}
        assert "contact" not in columns
        assert "contact_encrypted" in columns
        token = connection.execute(text("SELECT contact_encrypted FROM customers WHERE id = 1")).scalar_one()
        assert decrypt_text(token) == "555-0102-DUMMY"
        assert connection.execute(text("PRAGMA integrity_check")).scalar_one() == "ok"

    assert b"555-0102-DUMMY" not in database_path.read_bytes()
    backups = list(backup_dir.glob("*.db"))
    assert len(backups) == 1
    with engine.connect() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM customers")).scalar_one() == 1
    engine.dispose()


def test_customer_contact_migration_stops_if_backup_fails():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE customers (id INTEGER PRIMARY KEY, contact TEXT NOT NULL)")
        connection.exec_driver_sql("INSERT INTO customers (id, contact) VALUES (1, '555-0104-DUMMY')")

    with pytest.raises(RuntimeError, match="backup directory is required"):
        migrate_customer_contact_encryption(engine)

    with engine.connect() as connection:
        columns = {column["name"] for column in inspect(connection).get_columns("customers")}
        assert "contact_encrypted" not in columns
        assert connection.execute(text("SELECT contact FROM customers WHERE id = 1")).scalar_one() == "555-0104-DUMMY"
    engine.dispose()


def test_customer_contact_migration_requires_configured_backup_dir(tmp_path, monkeypatch):
    from app import config

    database_path = tmp_path / "requires-backup.db"
    engine = create_engine(f"sqlite:///{database_path}")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE customers (id INTEGER PRIMARY KEY, contact TEXT NOT NULL)")
        connection.exec_driver_sql("INSERT INTO customers (id, contact) VALUES (1, 'PRIVATE-TEST-DATA')")
    monkeypatch.setattr(config, "get_settings", lambda: type("Settings", (), {"backup_dir": None})())

    with pytest.raises(RuntimeError, match="BACKUP_DIR"):
        migrate_customer_contact_encryption(engine)
    with engine.connect() as connection:
        columns = {column["name"] for column in inspect(connection).get_columns("customers")}
        assert "contact" in columns
        assert "contact_encrypted" not in columns
    engine.dispose()


def test_customer_contact_migration_preserves_plaintext_if_round_trip_fails(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'failed.db'}")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE customers (id INTEGER PRIMARY KEY, contact TEXT NOT NULL)")
        connection.exec_driver_sql("INSERT INTO customers (id, contact) VALUES (1, '555-0105-DUMMY')")

    monkeypatch.setattr(migrations, "decrypt_text", lambda _token: "incorrect")
    with pytest.raises(RuntimeError, match="plaintext was not cleared"):
        migrate_customer_contact_encryption(engine, tmp_path / "failed-backups")

    with engine.connect() as connection:
        columns = {column["name"] for column in inspect(connection).get_columns("customers")}
        assert "contact" in columns
        assert connection.execute(text("SELECT contact FROM customers WHERE id = 1")).scalar_one() == "555-0105-DUMMY"
        assert connection.execute(text("SELECT contact_encrypted FROM customers WHERE id = 1")).scalar_one() is None
    engine.dispose()


def test_customer_api_returns_plaintext_to_owner_and_tokens_to_developer():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    app = FastAPI()
    app.include_router(customers_router)
    current_role = {"value": Role.owner}

    def override_db():
        with session_local() as db:
            yield db

    def override_role():
        return current_role["value"]

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_role] = override_role
    client = TestClient(app)
    try:
        created = client.post("/customers", json={"name": "Dummy Customer", "contact": "555-0103-DUMMY"})
        assert created.status_code == 201
        assert created.json() == {
            "id": 1,
            "name": "Dummy Customer",
            "contact": "555-0103-DUMMY",
            "is_masked": False,
        }

        with session_local() as db:
            stored = db.get(Customer, 1)
            assert stored.contact_encrypted is not None
            assert not hasattr(stored, "contact")
            assert decrypt_text(stored.name_encrypted) == "Dummy Customer"
            assert decrypt_text(stored.contact_encrypted) == "555-0103-DUMMY"

        assert client.get("/customers", params={"q": "dummy"}).json()[0]["id"] == 1
        assert client.get("/customers", params={"q": "absent"}).json() == []

        current_role["value"] = Role.developer
        developer_response = client.get("/customers")
        assert developer_response.status_code == 200
        customer = developer_response.json()[0]
        assert customer["is_masked"] is True
        assert customer["name"].startswith("gAAAA")
        assert customer["contact"].startswith("gAAAA")
        assert "ID #" not in customer["name"]
        assert client.get("/customers", params={"q": "dummy"}).status_code == 403
    finally:
        client.close()
        app.dependency_overrides.clear()
        engine.dispose()
