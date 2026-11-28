from datetime import date, datetime
import sqlite3

from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.migrations import (
    migrate_customer_area_encryption, migrate_finance_entries,
    migrate_input_product_mapping, migrate_products_stock,
    migrate_stock_documents, migrate_task_finance_fields,
    migrate_unified_insights, migrate_crop_type_product_mapping,
    migrate_activities, migrate_rename_tasks_to_activities,
)
from app.models import (
    Batch, CropCycle, CropType, Customer, InputApplication, InputItem, Insight, Product,
    Recommendation, Role, StockMovement, Table, Activity, User,
)
from app.services.products_stock import on_hand
from app.services.secure_fields import decrypt_text, encrypt_number, encrypt_text, hash_catalog_name


def _run_phase2_migrations(engine):
    migrate_rename_tasks_to_activities(engine)
    migrate_products_stock(engine)
    migrate_stock_documents(engine)
    migrate_crop_type_product_mapping(engine)
    migrate_input_product_mapping(engine)
    migrate_finance_entries(engine)
    migrate_task_finance_fields(engine)
    migrate_customer_area_encryption(engine)
    migrate_unified_insights(engine)
    migrate_activities(engine)


def test_phase2_migrations_upgrade_populated_phase1e_slice1b_schema_twice(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'phase1e-slice1b.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    product_name = "LEGACY_PRODUCT_2E91"
    customer_name = "LEGACY_CUSTOMER_2E91"
    input_name = "LEGACY_INPUT_2E91"
    task_title = "LEGACY_TASK_2E91"
    with Session() as db:
        db.add_all([
            User(id=1, username="owner", password_hash="unused", role=Role.owner),
            Table(id=1, table_number=1),
            Batch(id=1, batch_number=1, start_date=date(2026, 1, 1), week_offset=0),
            Product(
                id=1, category="vegetable", name_encrypted=encrypt_text(product_name).encode("ascii"),
                name_hash=hash_catalog_name(product_name), unit="kg", is_active=True,
            ),
            CropType(id=1, name="Legacy crop", nursery_days=10, growth_days=20),
        ])
        db.flush()
        db.add(CropCycle(
            id=1, table_id=1, batch_id=1, crop_type_id=1, nursery_start=date(2026, 1, 1),
            status="nursery", cycle_code="260101", harvest_quantity_kg=12,
        ))
        db.add_all([
            StockMovement(
                id=1, product_id=1, quantity_delta=12, movement_type="receipt",
                occurred_at=datetime(2026, 1, 2), note_encrypted=encrypt_text("legacy stock").encode("ascii"),
            ),
            Customer(
                id=1, name_encrypted=encrypt_text(customer_name).encode("ascii"),
                contact_encrypted=encrypt_text("LEGACY_CONTACT_2E91").encode("ascii"),
            ),
            InputApplication(
                id=1, cycle_id=1, applied_date=date(2026, 1, 2), category="fertilizer",
                note_encrypted=encrypt_text("legacy application").encode("ascii"),
            ),
            Activity(
                id=1, cycle_id=1, title=encrypt_text(task_title), planned_date=date(2026, 1, 3),
                status="pending", source="manual", is_encrypted=True,
            ),
            Recommendation(
                id=1, kind="recommendation", title="LEGACY_INSIGHT_TITLE_2E91",
                message="LEGACY_INSIGHT_BODY_2E91", reason="LEGACY_INSIGHT_REASON_2E91",
                status="pending",
            ),
        ])
        db.flush()
        db.add(InputItem(
            id=1, application_id=1, item_name_encrypted=encrypt_text(input_name).encode("ascii"),
            quantity_encrypted=encrypt_number("2.5").encode("ascii"), unit="kg",
        ))
        db.commit()

    # Rebuild the affected tables to match their populated pre-Phase-2 schema.
    engine.dispose()
    with sqlite3.connect(tmp_path / "phase1e-slice1b.db") as connection:
        connection.execute("PRAGMA foreign_keys=OFF")
        for table_name in (
            "insights", "finance_entries", "stock_document_lines", "stock_documents", "suppliers",
            "activity_targets", "activity_items", "harvest_entries", "change_notes", "push_devices", "notifications",
        ):
            connection.execute(f'DROP TABLE IF EXISTS "{table_name}"')
        # Before Phase 3 activities were stored as tasks with a due_date.
        connection.execute("ALTER TABLE activities RENAME TO tasks")
        connection.execute("ALTER TABLE tasks RENAME COLUMN planned_date TO due_date")
        for index_name in ("ix_activities_cycle_id", "ix_activities_planned_date", "ix_activities_status", "ix_activities_deleted_at", "ix_activities_kind", "uq_activities_open_stock_alert"):
            connection.execute(f'DROP INDEX IF EXISTS "{index_name}"')
        legacy_tables = {
            "crop_types": (
                "id, name, nursery_days, growth_days",
                "CREATE TABLE {name} (id INTEGER PRIMARY KEY, name VARCHAR(80) NOT NULL UNIQUE, "
                "nursery_days INTEGER NOT NULL, growth_days INTEGER NOT NULL)",
            ),
            "input_items": (
                "id, application_id, item_name_encrypted, quantity_encrypted, unit, created_at, updated_at",
                "CREATE TABLE {name} (id INTEGER PRIMARY KEY, application_id INTEGER NOT NULL, "
                "item_name_encrypted BLOB NOT NULL, quantity_encrypted BLOB NOT NULL, unit VARCHAR(80) NOT NULL, "
                "created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL, "
                "FOREIGN KEY(application_id) REFERENCES input_applications(id))",
            ),
            "input_catalog": (
                "id, name_encrypted, name_hash, last_unit, last_category, last_used_at, use_count",
                "CREATE TABLE {name} (id INTEGER PRIMARY KEY, name_encrypted BLOB NOT NULL, "
                "name_hash VARCHAR(64) NOT NULL UNIQUE, last_unit VARCHAR(80), last_category VARCHAR(80), "
                "last_used_at DATETIME, use_count INTEGER NOT NULL)",
            ),
            "customers": (
                "id, name_encrypted, contact_encrypted, created_at, updated_at, deleted_at",
                "CREATE TABLE {name} (id INTEGER PRIMARY KEY, name_encrypted BLOB NOT NULL, "
                "contact_encrypted BLOB, created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL, deleted_at DATETIME)",
            ),
            "tasks": (
                "id, cycle_id, title, due_date, status, source, is_encrypted, created_at, updated_at, deleted_at",
                "CREATE TABLE {name} (id INTEGER PRIMARY KEY, cycle_id INTEGER, title TEXT NOT NULL, "
                "due_date DATE NOT NULL, status VARCHAR(20) NOT NULL, source VARCHAR(20) NOT NULL, "
                "is_encrypted BOOLEAN NOT NULL, created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL, deleted_at DATETIME, "
                "FOREIGN KEY(cycle_id) REFERENCES crop_cycles(id) ON DELETE CASCADE)",
            ),
        }
        for table_name, (columns, create_sql) in legacy_tables.items():
            temp_name = f"{table_name}_legacy_tmp"
            connection.execute(create_sql.format(name=temp_name))
            connection.execute(f'INSERT INTO "{temp_name}" ({columns}) SELECT {columns} FROM "{table_name}"')
            connection.execute(f'DROP TABLE "{table_name}"')
            connection.execute(create_sql.format(name=table_name))
            connection.execute(f'INSERT INTO "{table_name}" ({columns}) SELECT {columns} FROM "{temp_name}"')
            connection.execute(f'DROP TABLE "{temp_name}"')
        connection.execute("CREATE INDEX ix_input_items_application_id ON input_items(application_id)")
        connection.execute("CREATE INDEX ix_tasks_cycle_id ON tasks(cycle_id)")
        connection.execute("CREATE INDEX ix_tasks_due_date ON tasks(due_date)")
        connection.execute("CREATE INDEX ix_tasks_status ON tasks(status)")
        connection.execute("CREATE INDEX ix_tasks_deleted_at ON tasks(deleted_at)")
    engine = create_engine(f"sqlite:///{tmp_path / 'phase1e-slice1b.db'}")
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    assert "finance_entries" not in inspect(engine).get_table_names()
    assert "product_id" not in {column["name"] for column in inspect(engine).get_columns("crop_types")}
    _run_phase2_migrations(engine)
    _run_phase2_migrations(engine)

    with Session() as db:
        assert db.scalar(select(Product.id).where(Product.id == 1)) == 1
        assert on_hand(db, 1) == 12
        assert decrypt_text(db.get(Product, 1).name_encrypted) == product_name
        assert decrypt_text(db.get(Customer, 1).name_encrypted) == customer_name
        assert decrypt_text(db.get(InputItem, 1).item_name_encrypted) == input_name
        assert decrypt_text(db.get(Activity, 1).title) == task_title
        assert db.scalar(select(CropType.product_id).where(CropType.id == 1)) is None
        assert db.scalar(select(InputItem.product_id).where(InputItem.id == 1)) is None
        assert db.scalar(select(Customer.area_encrypted).where(Customer.id == 1)) is None
        insights = db.scalars(select(Insight)).all()
        assert len(insights) == 1
        assert decrypt_text(insights[0].title_encrypted) == "LEGACY_INSIGHT_TITLE_2E91"
        assert "LEGACY_INSIGHT_BODY_2E91" in decrypt_text(insights[0].body_encrypted)
        assert db.scalar(text("SELECT COUNT(*) FROM recommendations")) == 1
    assert inspect(engine).has_table("stock_documents")
    assert "tasks" not in inspect(engine).get_table_names()
    assert {column["name"] for column in inspect(engine).get_columns("activities")} >= {
        "labor_cost_encrypted", "worker_count", "extra_cost_encrypted", "stock_alert_product_id",
        "kind", "planned_date", "started_on", "done_on", "remind", "note_encrypted",
    }
    engine.dispose()
