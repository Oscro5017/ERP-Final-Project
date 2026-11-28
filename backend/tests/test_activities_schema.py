"""Phase 3 step 1: tasks become activities, new planning tables, and change notes."""
import sqlite3
from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.engine import URL
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.migrations import migrate_activities, migrate_rename_tasks_to_activities
from app.models import Activity, ChangeNote, CropType, Role, Table, User
from app.services.change_notes import list_changes, record_change, record_changes
from app.services.secure_fields import encrypt_text

# The tasks table as Phase 2 left it.
PHASE2_TASKS = """
CREATE TABLE products (id INTEGER PRIMARY KEY);
CREATE TABLE tables (id INTEGER PRIMARY KEY, table_number INTEGER NOT NULL UNIQUE);
CREATE TABLE crop_types (
    id INTEGER PRIMARY KEY, name VARCHAR(80) NOT NULL UNIQUE, nursery_days INTEGER NOT NULL,
    growth_days INTEGER NOT NULL, product_id INTEGER REFERENCES products(id) ON DELETE SET NULL
);
CREATE TABLE crop_cycles (id INTEGER PRIMARY KEY, table_id INTEGER REFERENCES tables(id));
CREATE TABLE tasks (
    id INTEGER NOT NULL PRIMARY KEY, cycle_id INTEGER REFERENCES crop_cycles(id) ON DELETE CASCADE,
    title TEXT NOT NULL, due_date DATE NOT NULL, status VARCHAR(20) NOT NULL DEFAULT 'pending',
    source VARCHAR(20) NOT NULL DEFAULT 'manual', created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL, deleted_at DATETIME, is_encrypted BOOLEAN NOT NULL DEFAULT 0,
    labor_cost_encrypted BLOB, worker_count INTEGER, extra_cost_encrypted BLOB,
    stock_alert_product_id INTEGER REFERENCES products(id) ON DELETE SET NULL
);
CREATE INDEX ix_tasks_cycle_id ON tasks(cycle_id);
CREATE INDEX ix_tasks_due_date ON tasks(due_date);
CREATE INDEX ix_tasks_status ON tasks(status);
CREATE INDEX ix_tasks_deleted_at ON tasks(deleted_at);
CREATE UNIQUE INDEX uq_tasks_open_stock_alert ON tasks(stock_alert_product_id)
    WHERE stock_alert_product_id IS NOT NULL AND status = 'pending' AND deleted_at IS NULL;
CREATE TABLE sales_order_lines (
    id INTEGER PRIMARY KEY, planting_task_id INTEGER REFERENCES tasks(id) ON DELETE SET NULL
);
CREATE TABLE insights (id INTEGER PRIMARY KEY, task_id INTEGER REFERENCES tasks(id) ON DELETE SET NULL);
"""


def _tasks_table_only():
    """Only the Phase 2 tasks table and its indexes; startup creates everything else."""
    start = PHASE2_TASKS.index("CREATE TABLE tasks")
    return PHASE2_TASKS[start:PHASE2_TASKS.index("CREATE TABLE sales_order_lines")]


def _phase2_database(path):
    manual_title = encrypt_text("ย้ายปลูก งานที่เจ้าของพิมพ์เอง")
    with sqlite3.connect(path) as connection:
        connection.executescript(PHASE2_TASKS)
        connection.executescript("""
            INSERT INTO products (id) VALUES (1);
            INSERT INTO tables (id, table_number) VALUES (1, 7);
            INSERT INTO crop_types (id, name, nursery_days, growth_days) VALUES (1, 'กรีนโอ๊ค', 14, 28);
            INSERT INTO crop_cycles (id, table_id) VALUES (1, 1);
        """)
        rows = [
            (1, 1, "ย้ายปลูก โต๊ะ 7", "2026-11-01", "done", "auto", 0, None),
            (2, 1, "เตรียมเก็บเกี่ยว โต๊ะ 7", "2026-11-29", "pending", "auto", 0, None),
            (3, 1, "ทำความสะอาดโต๊ะ 7", "2026-12-01", "pending", "auto", 0, None),
            (4, None, encrypt_text("ของใกล้หมด: ปุ๋ย"), "2026-11-20", "pending", "auto", 1, 1),
            (5, None, "เพาะกล้า กรีนโอ๊ค 10 kg ตามออเดอร์ SO-1", "2026-11-25", "pending", "auto", 0, None),
            (6, 1, manual_title, "2026-11-21", "pending", "manual", 1, None),
        ]
        connection.executemany(
            "INSERT INTO tasks (id, cycle_id, title, due_date, status, source, is_encrypted, stock_alert_product_id, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, '2026-11-01', '2026-11-01')",
            rows,
        )
        connection.execute("INSERT INTO sales_order_lines (id, planting_task_id) VALUES (1, 5)")
        connection.execute("INSERT INTO insights (id, task_id) VALUES (1, 2)")
    return create_engine(URL.create("sqlite", database=str(path)))


def _upgrade(engine):
    migrate_rename_tasks_to_activities(engine)
    migrate_activities(engine)


def test_upgrade_renames_tasks_keeps_rows_and_rewrites_foreign_keys(tmp_path):
    engine = _phase2_database(tmp_path / "phase2.db")

    _upgrade(engine)
    _upgrade(engine)  # idempotent

    names = set(inspect(engine).get_table_names())
    assert "tasks" not in names and "activities" in names
    columns = {column["name"] for column in inspect(engine).get_columns("activities")}
    assert "due_date" not in columns
    assert {"planned_date", "kind", "started_on", "done_on", "remind", "note_encrypted"} <= columns
    with engine.connect() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM activities")).scalar() == 6
        assert connection.execute(text("SELECT planned_date FROM activities WHERE id = 2")).scalar() == "2026-11-29"
        assert connection.execute(text("SELECT remind FROM activities WHERE id = 1")).scalar() == 0
        for table_name in ("sales_order_lines", "insights"):
            targets = {row[2] for row in connection.exec_driver_sql(f"PRAGMA foreign_key_list({table_name})")}
            assert targets == {"activities"}
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall() == []
        assert connection.exec_driver_sql("PRAGMA integrity_check").scalar() == "ok"
    engine.dispose()


def test_upgrade_gives_old_activities_the_kind_their_origin_implies(tmp_path):
    engine = _phase2_database(tmp_path / "phase2.db")
    _upgrade(engine)
    with engine.connect() as connection:
        kinds = dict(connection.execute(text("SELECT id, kind FROM activities ORDER BY id")).all())
    assert kinds == {
        1: "transplant",
        2: "harvest",
        3: "cleanup",
        4: "stock_alert",
        5: "order_planting",
        6: "general",  # the owner's own encrypted title is never guessed from its words
    }
    engine.dispose()


def test_upgrade_replaces_task_indexes_with_activity_indexes(tmp_path):
    engine = _phase2_database(tmp_path / "phase2.db")
    _upgrade(engine)
    index_names = {index["name"] for index in inspect(engine).get_indexes("activities")}
    assert not any(name.startswith(("ix_tasks_", "uq_tasks_")) for name in index_names)
    assert {
        "ix_activities_cycle_id", "ix_activities_planned_date", "ix_activities_status",
        "ix_activities_deleted_at", "ix_activities_kind", "uq_activities_open_stock_alert",
    } <= index_names
    with engine.begin() as connection:
        # The open stock-alert rule still holds after the rename.
        try:
            connection.execute(text(
                "INSERT INTO activities (title, planned_date, status, source, is_encrypted, stock_alert_product_id, "
                "created_at, updated_at) VALUES ('dup', '2026-11-22', 'pending', 'auto', 0, 1, '2026-11-01', '2026-11-01')"
            ))
            raise AssertionError("a second open stock alert for one product was accepted")
        except Exception as exc:  # sqlite3.IntegrityError wrapped by SQLAlchemy
            assert "UNIQUE" in str(exc)
    engine.dispose()


def test_upgrade_adds_planning_columns_to_cycles_crop_types_and_tables(tmp_path):
    engine = _phase2_database(tmp_path / "phase2.db")
    _upgrade(engine)
    inspector = inspect(engine)
    assert {"seed_count", "plant_count", "expected_transplant_on", "expected_ready_on"} <= {
        column["name"] for column in inspector.get_columns("crop_cycles")
    }
    assert "seed_product_id" in {column["name"] for column in inspector.get_columns("crop_types")}
    with engine.connect() as connection:
        assert connection.execute(text("SELECT capacity_plants FROM tables WHERE id = 1")).scalar() == 200
    engine.dispose()


def test_startup_on_phase2_database_renames_instead_of_creating_an_empty_table(tmp_path, monkeypatch):
    from cryptography.fernet import Fernet

    from app.config import Settings
    from tests.test_legacy_data_migration import _run_app_startup_with_engine

    path = tmp_path / "startup.db"
    with sqlite3.connect(path) as connection:
        connection.executescript(_tasks_table_only())
        connection.execute(
            "INSERT INTO tasks (id, title, due_date, status, source, created_at, updated_at) "
            "VALUES (1, 'ล้างถังน้ำ', '2026-11-20', 'pending', 'auto', '2026-11-01', '2026-11-01')"
        )
    engine = create_engine(URL.create("sqlite", database=str(path)))
    settings = Settings(_env_file=None, encryption_key=Fernet.generate_key().decode(), backup_dir=str(tmp_path / "backups"))

    _run_app_startup_with_engine(monkeypatch, engine, settings)

    assert "tasks" not in inspect(engine).get_table_names()
    with engine.connect() as connection:
        assert connection.execute(text("SELECT title, planned_date, kind FROM activities")).all() == [
            ("ล้างถังน้ำ", "2026-11-20", "general"),
        ]
    engine.dispose()


def _session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False)()


def test_new_database_has_activity_tables_and_table_capacity_default():
    db = _session()
    names = set(inspect(db.get_bind()).get_table_names())
    assert {
        "activities", "activity_targets", "activity_items", "harvest_entries",
        "change_notes", "push_devices", "notifications",
    } <= names
    assert "tasks" not in names
    db.add(Table(table_number=1))
    db.add(CropType(name="ผักกาด", nursery_days=10, growth_days=30))
    db.commit()
    assert db.scalar(select(Table.capacity_plants)) == 200
    assert db.scalar(select(CropType.seed_product_id)) is None


def test_stage_activities_are_created_with_their_kind():
    from app.models import Batch, CropCycle, CycleStatus
    from app.services.task_generator import sync_crop_cycle_tasks

    db = _session()
    db.add_all([
        Table(id=1, table_number=3),
        Batch(id=1, batch_number=1, start_date=date(2026, 11, 1)),
        CropType(id=1, name="คะน้า", nursery_days=10, growth_days=30),
    ])
    db.flush()
    cycle = CropCycle(table_id=1, batch_id=1, crop_type_id=1, nursery_start=date(2026, 11, 1), status=CycleStatus.nursery)
    db.add(cycle)
    db.flush()
    sync_crop_cycle_tasks(db, cycle)
    db.flush()
    cycle.status = CycleStatus.bushed
    sync_crop_cycle_tasks(db, cycle)
    db.flush()

    rows = db.execute(select(Activity.kind, Activity.status, Activity.planned_date).order_by(Activity.id)).all()
    assert rows == [
        ("transplant", "done", date(2026, 11, 11)),
        ("harvest", "pending", date(2026, 12, 11)),
    ]


def test_change_notes_skip_unchanged_values_and_store_everything_encrypted():
    db = _session()
    owner = User(username="owner", password_hash="x", role=Role.owner)
    db.add(owner)
    db.flush()

    notes = record_changes(
        db,
        entity_type="crop_cycle",
        entity_id=9,
        before={"plant_count": 180, "status": "nursery", "harvest_quantity_kg": 1.5},
        after={"plant_count": 150, "status": "nursery", "harvest_quantity_kg": Decimal("1.50")},
        user_id=owner.id,
        reason="  ต้นกล้าตาย 30 ต้น  ",
        auto_notes={"plant_count": "ระบบจดอัตโนมัติ"},
    )
    db.commit()

    assert [note.field for note in notes] == ["plant_count"]
    raw = db.execute(text("SELECT old_value_encrypted, new_value_encrypted, reason_encrypted FROM change_notes")).one()
    assert all(b"180" not in value and "ต้นกล้า".encode() not in value for value in raw)

    [shown] = list_changes(db, "crop_cycle", 9, Role.owner)
    assert (shown.field, shown.old_value, shown.new_value) == ("plant_count", "180", "150")
    assert shown.reason == "ต้นกล้าตาย 30 ต้น"
    assert shown.auto_note == "ระบบจดอัตโนมัติ"
    assert shown.user_id == owner.id
    assert shown.is_masked is False


def test_change_notes_are_masked_for_the_developer_and_blank_reasons_are_dropped():
    db = _session()
    record_change(
        db, entity_type="activity", entity_id=1, field="planned_date",
        old=date(2026, 11, 1), new=date(2026, 11, 3), reason="   ",
    )
    db.commit()

    [shown] = list_changes(db, "activity", 1, Role.developer)
    assert shown.is_masked is True
    assert shown.old_value not in (None, "2026-11-01")
    assert shown.new_value not in (None, "2026-11-03")
    assert shown.reason is None
    assert db.scalar(select(ChangeNote.reason_encrypted)) is None
    assert list_changes(db, "activity", 2, Role.owner) == []
