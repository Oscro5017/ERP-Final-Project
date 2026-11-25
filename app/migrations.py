import logging
import os
import sqlite3
import subprocess
from datetime import date
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from .services.secure_fields import decrypt_number, decrypt_text, encrypt_number, encrypt_text, hash_catalog_name
from .models import (
    CropCycleStatusLog,
    CropType,
    FinanceEntry,
    Insight,
    Recommendation,
    Product,
    StockDocument,
    StockDocumentLine,
    StockMovement,
    Supplier,
    SystemMeta,
)

logger = logging.getLogger(__name__)


def migrate_system_meta(engine: Engine) -> None:
    """Create the additive canary metadata table without backing up existing data."""
    SystemMeta.__table__.create(bind=engine, checkfirst=True)


def migrate_products_stock(engine: Engine) -> None:
    """Create product and stock ledger tables additively and idempotently."""
    Product.__table__.create(bind=engine, checkfirst=True)
    StockMovement.__table__.create(bind=engine, checkfirst=True)


def migrate_stock_documents(engine: Engine) -> None:
    """Create supplier and stock document tables additively and idempotently."""
    for model in (Supplier, StockDocument, StockDocumentLine):
        model.__table__.create(bind=engine, checkfirst=True)


def migrate_crop_type_product_mapping(engine: Engine) -> None:
    """Add the optional crop output mapping without rewriting existing crop types."""
    inspector = inspect(engine)
    if "crop_types" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("crop_types")}
    if "product_id" not in columns:
        with engine.begin() as connection:
            connection.execute(text(
                "ALTER TABLE crop_types ADD COLUMN product_id INTEGER "
                "REFERENCES products(id) ON DELETE SET NULL"
            ))
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_crop_types_product_id "
            "ON crop_types(product_id)"
        ))


def migrate_input_product_mapping(engine: Engine) -> None:
    """Add optional product mappings to input items and their reusable catalog."""
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    for table_name in ("input_items", "input_catalog"):
        if table_name not in tables:
            continue
        columns = {column["name"] for column in inspect(engine).get_columns(table_name)}
        if "product_id" not in columns:
            with engine.begin() as connection:
                connection.execute(text(
                    f"ALTER TABLE {table_name} ADD COLUMN product_id INTEGER "
                    "REFERENCES products(id) ON DELETE SET NULL"
                ))


def migrate_finance_entries(engine: Engine) -> None:
    """Create the additive finance ledger table and its query indexes."""
    FinanceEntry.__table__.create(bind=engine, checkfirst=True)


def migrate_task_finance_fields(engine: Engine) -> None:
    """Add optional encrypted task costs and worker count without changing rows."""
    inspector = inspect(engine)
    if "tasks" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("tasks")}
    additions = {
        "labor_cost_encrypted": "BLOB",
        "worker_count": "INTEGER",
        "extra_cost_encrypted": "BLOB",
        "stock_alert_product_id": "INTEGER REFERENCES products(id) ON DELETE SET NULL",
    }
    with engine.begin() as connection:
        for name, column_type in additions.items():
            if name not in columns:
                connection.execute(text(f"ALTER TABLE tasks ADD COLUMN {name} {column_type}"))
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_tasks_open_stock_alert "
            "ON tasks(stock_alert_product_id) "
            "WHERE stock_alert_product_id IS NOT NULL AND status = 'pending' AND deleted_at IS NULL"
        ))


def migrate_customer_area_encryption(engine: Engine) -> None:
    """Add an optional encrypted customer area field without rewriting existing data."""
    inspector = inspect(engine)
    if "customers" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("customers")}
    if "area_encrypted" not in columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE customers ADD COLUMN area_encrypted BLOB"))


def migrate_unified_insights(engine: Engine) -> None:
    """Create the encrypted unified insight table and copy legacy recommendations once."""
    Insight.__table__.create(bind=engine, checkfirst=True)
    if not inspect(engine).has_table(Recommendation.__tablename__):
        return
    with engine.begin() as connection:
        rows = connection.execute(text(
            "SELECT id, kind, title, message, reason, window_start, window_end, status, task_id, created_at, updated_at "
            "FROM recommendations ORDER BY id"
        )).mappings().all()
        for row in rows:
            if connection.scalar(text(
                "SELECT id FROM insights WHERE legacy_recommendation_id = :legacy_id"
            ), {"legacy_id": row["id"]}) is not None:
                continue
            old_kind = str(row["kind"] or "recommendation").casefold()
            kind = old_kind if old_kind in {"insight", "recommendation", "alert"} else "recommendation"
            old_status = str(row["status"] or "new").casefold()
            status = old_status if old_status in {"new", "seen", "dismissed", "done"} else ("done" if old_status == "completed" else "new")
            task_id = row["task_id"]
            cycle_id = connection.scalar(text("SELECT cycle_id FROM tasks WHERE id = :task_id"), {"task_id": task_id}) if task_id else None
            body_parts = [str(row["message"] or "").strip()]
            reason = str(row["reason"] or "").strip()
            if reason:
                body_parts.append(f"เหตุผล: {reason}")
            body = "\n\n".join(part for part in body_parts if part)
            connection.execute(text(
                "INSERT INTO insights (kind, source, title_encrypted, body_encrypted, severity, valid_from, valid_until, "
                "crop_cycle_id, task_id, status, legacy_recommendation_id, created_at, updated_at) "
                "VALUES (:kind, 'rule', :title, :body, 'info', :valid_from, :valid_until, :cycle_id, :task_id, :status, :legacy_id, :created_at, :updated_at)"
            ), {
                "kind": kind,
                "title": encrypt_text(str(row["title"] or "")).encode("ascii"),
                "body": encrypt_text(body).encode("ascii"),
                "valid_from": row["window_start"],
                "valid_until": row["window_end"],
                "cycle_id": cycle_id,
                "task_id": task_id,
                "status": status,
                "legacy_id": row["id"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            })


def _configured_backup_dir(backup_dir: Path | str | None) -> Path:
    if backup_dir is None:
        from .config import get_settings

        backup_dir = get_settings().backup_dir
    if not backup_dir:
        raise RuntimeError("An explicit backup directory is required; set BACKUP_DIR before running this migration.")
    return Path(backup_dir).expanduser().resolve()


def _best_effort_secure_backup_path(path: Path, is_directory: bool = True) -> None:
    try:
        _secure_phase1e_backup_path(path, is_directory=is_directory)
    except (OSError, subprocess.SubprocessError):
        logger.warning("Could not fully restrict permissions on migration backup path %s.", path)


def _backup_sqlite_database(engine: Engine, backup_dir: Path | str | None = None) -> Path:
    if engine.dialect.name != "sqlite":
        raise RuntimeError("Customer contact migration stopped: automatic backup is only configured for SQLite.")

    destination_dir = _configured_backup_dir(backup_dir)
    database = engine.url.database
    backup_name = f"erp-pre-phase1d-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}.db"
    if database and database != ":memory:":
        database_path = Path(database).resolve()
        backup_name = f"{database_path.stem}-pre-phase1d-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}.db"
    destination = destination_dir / backup_name

    try:
        destination_dir.mkdir(parents=True, exist_ok=True)
        _best_effort_secure_backup_path(destination_dir)
        destination_connection = sqlite3.connect(destination)
        try:
            raw_connection = engine.raw_connection()
            try:
                raw_connection.driver_connection.backup(destination_connection)
            finally:
                raw_connection.close()
        finally:
            destination_connection.close()

        if os.name != "nt":
            destination.chmod(0o600)
        else:
            _best_effort_secure_backup_path(destination, is_directory=False)

        verification_connection = sqlite3.connect(destination)
        try:
            integrity = verification_connection.execute("PRAGMA integrity_check").fetchone()
        finally:
            verification_connection.close()
        if integrity is None or integrity[0] != "ok":
            raise RuntimeError("SQLite backup integrity check failed.")
    except Exception as exc:
        destination.unlink(missing_ok=True)
        raise RuntimeError("Customer contact migration stopped because the database backup failed.") from exc

    logger.warning(
        "Created a restricted pre-Phase 1d backup at %s. It may contain plaintext farm data; keep it private and outside the repository.",
        destination,
    )
    return destination


def _drop_plaintext_customer_contact(connection) -> None:
    table_info = connection.exec_driver_sql("PRAGMA table_info(customers)").mappings().all()
    indexes = connection.exec_driver_sql(
        "SELECT sql FROM sqlite_master WHERE type = 'index' AND tbl_name = 'customers' AND sql IS NOT NULL"
    ).scalars().all()
    kept_columns = [column for column in table_info if column["name"] != "contact"]
    definitions = []
    names = []
    for column in kept_columns:
        quoted_name = '"' + column["name"].replace('"', '""') + '"'
        definition = f"{quoted_name} {column['type']}"
        if column["pk"]:
            definition += " PRIMARY KEY"
        elif column["notnull"]:
            definition += " NOT NULL"
        if column["dflt_value"] is not None:
            definition += f" DEFAULT {column['dflt_value']}"
        definitions.append(definition)
        names.append(quoted_name)

    connection.exec_driver_sql(f"CREATE TABLE customers_phase1d ({', '.join(definitions)})")
    column_list = ", ".join(names)
    connection.exec_driver_sql(
        f"INSERT INTO customers_phase1d ({column_list}) SELECT {column_list} FROM customers"
    )
    connection.exec_driver_sql("DROP TABLE customers")
    connection.exec_driver_sql("ALTER TABLE customers_phase1d RENAME TO customers")
    for index_sql in indexes:
        connection.exec_driver_sql(index_sql)


def _vacuum_sqlite_database(engine: Engine, force: bool = False) -> None:
    if engine.dialect.name != "sqlite":
        return
    raw_connection = engine.raw_connection()
    database_connection = raw_connection.driver_connection
    try:
        freelist_pages = database_connection.execute("PRAGMA freelist_count").fetchone()[0]
        if force or freelist_pages:
            original_isolation_level = database_connection.isolation_level
            database_connection.isolation_level = None
            try:
                database_connection.execute("VACUUM")
                if database_connection.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal":
                    database_connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            finally:
                database_connection.isolation_level = original_isolation_level
    finally:
        raw_connection.close()


def migrate_customer_contact_encryption(engine: Engine, backup_dir: Path | None = None) -> int:
    inspector = inspect(engine)
    if "customers" not in inspector.get_table_names():
        return 0

    columns = {column["name"] for column in inspector.get_columns("customers")}
    has_legacy_contact = "contact" in columns
    needs_column = "contact_encrypted" not in columns
    if has_legacy_contact:
        with engine.connect() as connection:
            plaintext_exists = connection.execute(
                text("SELECT 1 FROM customers WHERE contact IS NOT NULL LIMIT 1")
            ).first() is not None
    else:
        plaintext_exists = False

    if not needs_column and not plaintext_exists and not has_legacy_contact:
        logger.info("Customer contact migration already complete; no plaintext rows found.")
        _vacuum_sqlite_database(engine)
        return 0

    _backup_sqlite_database(engine, backup_dir)

    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA secure_delete = ON")
        if needs_column:
            connection.execute(text("ALTER TABLE customers ADD COLUMN contact_encrypted BLOB"))

        current_columns = {column["name"] for column in inspect(connection).get_columns("customers")}
        if "contact" not in current_columns:
            return 0

        rows = connection.execute(
            text("SELECT id, contact, contact_encrypted FROM customers WHERE contact IS NOT NULL")
        ).mappings().all()
        migrated: list[tuple[int, bytes]] = []
        for row in rows:
            try:
                if row["contact_encrypted"] is not None:
                    token = row["contact_encrypted"]
                    if isinstance(token, bytes):
                        token = token.decode("ascii")
                    if decrypt_text(token) != row["contact"]:
                        raise ValueError("Existing token does not match legacy contact.")
                else:
                    token = encrypt_text(row["contact"])
                    if decrypt_text(token) != row["contact"]:
                        raise ValueError("New token failed round-trip validation.")
                migrated.append((row["id"], token.encode("ascii")))
            except Exception as exc:
                logger.error("Customer contact encryption round-trip failed for customer id %s.", row["id"])
                raise RuntimeError(
                    f"Customer contact migration aborted at customer id {row['id']}; plaintext was not cleared."
                ) from exc

        for customer_id, token in migrated:
            connection.execute(
                text("UPDATE customers SET contact_encrypted = :token WHERE id = :id"),
                {"token": token, "id": customer_id},
            )
        _drop_plaintext_customer_contact(connection)

    _vacuum_sqlite_database(engine, force=True)
    logger.info("Encrypted and verified %s customer contact rows.", len(migrated))
    return len(migrated)


def migrate_crop_cycles(engine: Engine) -> None:
    inspector = inspect(engine)
    if "crop_cycles" not in inspector.get_table_names():
        return

    with engine.begin() as connection:
        columns = {column["name"] for column in inspector.get_columns("crop_cycles")}
        if "cycle_code" not in columns:
            connection.execute(text("ALTER TABLE crop_cycles ADD COLUMN cycle_code VARCHAR(6)"))

        if engine.dialect.name == "postgresql":
            for value in ("bushed", "ready_to_harvest", "empty"):
                connection.execute(text(f"ALTER TYPE cycle_status ADD VALUE IF NOT EXISTS '{value}'"))

        legacy_rows = connection.execute(
            text("SELECT id, status, nursery_start FROM crop_cycles WHERE status IN (:fertilizing, :treating, :transplanted, :cleaning)"),
            {"fertilizing": "fertilizing", "treating": "treating", "transplanted": "transplanted", "cleaning": "cleaning"},
        ).mappings().all()
        status_map = {
            "transplanted": "bushed",
            "fertilizing": "bushed",
            "treating": "bushed",
            "cleaning": "empty",
        }
        for row in legacy_rows:
            mapped_status = status_map[row["status"]]
            logger.warning(
                "Mapped legacy CropCycle %s status %s to %s; verify this historical status.",
                row["id"], row["status"], mapped_status,
            )
            connection.execute(
                text("UPDATE crop_cycles SET status = :status WHERE id = :id"),
                {"status": mapped_status, "id": row["id"]},
            )

        rows_without_codes = connection.execute(
            text("SELECT id, nursery_start FROM crop_cycles WHERE cycle_code IS NULL OR cycle_code = ''")
        ).mappings().all()
        for row in rows_without_codes:
            start_date = row["nursery_start"]
            if isinstance(start_date, str):
                start_date = date.fromisoformat(start_date)
            connection.execute(
                text("UPDATE crop_cycles SET cycle_code = :cycle_code WHERE id = :id"),
                {"cycle_code": start_date.strftime("%y%m%d"), "id": row["id"]},
            )


def migrate_phase1c(engine: Engine) -> None:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if "crop_cycles" not in tables:
        return

    additions = {
        "crop_cycles": {
            "harvest_quantity_kg": "FLOAT",
            "created_at": "TIMESTAMP",
            "updated_at": "TIMESTAMP",
            "deleted_at": "TIMESTAMP",
        },
        "customers": {"created_at": "TIMESTAMP", "updated_at": "TIMESTAMP", "deleted_at": "TIMESTAMP"},
        "input_applications": {"created_at": "TIMESTAMP", "updated_at": "TIMESTAMP", "deleted_at": "TIMESTAMP"},
        "input_items": {"created_at": "TIMESTAMP", "updated_at": "TIMESTAMP"},
        "tasks": {"updated_at": "TIMESTAMP", "deleted_at": "TIMESTAMP"},
        "weather_logs": {"created_at": "TIMESTAMP", "updated_at": "TIMESTAMP"},
    }

    with engine.begin() as connection:
        for table_name, columns_to_add in additions.items():
            if table_name not in tables:
                continue
            existing_columns = {column["name"] for column in inspect(connection).get_columns(table_name)}
            for column_name, column_type in columns_to_add.items():
                if column_name not in existing_columns:
                    connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"))

            timestamp_columns = {column["name"] for column in inspect(connection).get_columns(table_name)}
            if "created_at" in timestamp_columns:
                connection.execute(text(f"UPDATE {table_name} SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL"))
            if "updated_at" in timestamp_columns:
                fallback = "COALESCE(created_at, CURRENT_TIMESTAMP)" if "created_at" in timestamp_columns else "CURRENT_TIMESTAMP"
                connection.execute(text(f"UPDATE {table_name} SET updated_at = {fallback} WHERE updated_at IS NULL"))
            if "deleted_at" in timestamp_columns:
                connection.execute(text(f"CREATE INDEX IF NOT EXISTS ix_{table_name}_deleted_at ON {table_name} (deleted_at)"))

        CropCycleStatusLog.__table__.create(connection, checkfirst=True)
        connection.execute(text("""
            INSERT INTO crop_cycle_status_logs (cycle_id, from_status, to_status, changed_at)
            SELECT cycle.id, NULL, cycle.status, COALESCE(cycle.created_at, CURRENT_TIMESTAMP)
            FROM crop_cycles AS cycle
            WHERE NOT EXISTS (
                SELECT 1 FROM crop_cycle_status_logs AS log WHERE log.cycle_id = cycle.id
            )
        """))


def _secure_phase1e_backup_path(path: Path, is_directory: bool = True) -> None:
    if os.name == "nt":
        identity = subprocess.run(
            ["whoami"], check=True, capture_output=True, text=True
        ).stdout.strip()
        subprocess.run(
            [
                "icacls", str(path), "/inheritance:r", "/grant:r",
                f"{identity}:(OI)(CI)F" if is_directory else f"{identity}:F",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    else:
        path.chmod(0o700)


def _backup_phase1e_database(engine: Engine, backup_dir: Path | str | None = None) -> Path:
    if engine.dialect.name != "sqlite":
        raise RuntimeError("Phase 1e migration stopped: automatic backup is only configured for SQLite.")

    destination_dir = _configured_backup_dir(backup_dir)
    backup_name = f"erp-pre-phase1e-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}.db"

    destination_dir.mkdir(parents=True, exist_ok=True)
    _best_effort_secure_backup_path(destination_dir)
    destination = destination_dir / backup_name
    try:
        destination_connection = sqlite3.connect(destination)
        try:
            raw_connection = engine.raw_connection()
            try:
                raw_connection.driver_connection.backup(destination_connection)
            finally:
                raw_connection.close()
        finally:
            destination_connection.close()
        if os.name != "nt":
            destination.chmod(0o600)
        else:
            _best_effort_secure_backup_path(destination, is_directory=False)
        verification_connection = sqlite3.connect(destination)
        try:
            integrity = verification_connection.execute("PRAGMA integrity_check").fetchone()
        finally:
            verification_connection.close()
        if integrity is None or integrity[0] != "ok":
            raise RuntimeError("SQLite backup integrity check failed.")
    except Exception as exc:
        destination.unlink(missing_ok=True)
        raise RuntimeError("Phase 1e migration stopped because a restricted database backup failed.") from exc

    logger.warning(
        "Created a restricted pre-Phase 1e backup at %s. It contains plaintext farm inputs; keep it private and outside the repository.",
        destination,
    )
    return destination


def migrate_phase1e(engine: Engine, backup_dir: Path | str | None = None) -> dict[str, int]:
    if engine.dialect.name != "sqlite":
        raise RuntimeError("Phase 1e migration currently supports SQLite only.")

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    required = {"input_applications", "input_items", "input_catalog", "tasks"}
    if not required.issubset(tables):
        return {"input_items": 0, "applications": 0, "catalog": 0, "tasks": 0}

    columns = {
        table: {column["name"] for column in inspector.get_columns(table)}
        for table in required
    }
    needs_migration = any((
        {"item_name", "quantity"} & columns["input_items"],
        "note" in columns["input_applications"],
        "item_name" in columns["input_catalog"],
        "is_encrypted" not in columns["tasks"],
    ))
    if not needs_migration:
        return {"input_items": 0, "applications": 0, "catalog": 0, "tasks": 0}

    _backup_phase1e_database(engine, backup_dir)
    counts = {"input_items": 0, "applications": 0, "catalog": 0, "tasks": 0}
    raw_connection = engine.raw_connection()
    connection = raw_connection.driver_connection
    try:
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute("PRAGMA secure_delete = ON")
        connection.execute("BEGIN IMMEDIATE")

        item_rows = connection.execute("SELECT * FROM input_items ORDER BY id").fetchall()
        app_rows = connection.execute("SELECT * FROM input_applications ORDER BY id").fetchall()
        catalog_rows = connection.execute("SELECT * FROM input_catalog ORDER BY id").fetchall()
        task_rows = connection.execute("SELECT * FROM tasks ORDER BY id").fetchall()
        item_names = [row[1] for row in connection.execute("PRAGMA table_info(input_items)")]
        app_names = [row[1] for row in connection.execute("PRAGMA table_info(input_applications)")]
        catalog_names = [row[1] for row in connection.execute("PRAGMA table_info(input_catalog)")]
        task_names = [row[1] for row in connection.execute("PRAGMA table_info(tasks)")]
        item_rows = [dict(zip(item_names, row)) for row in item_rows]
        app_rows = [dict(zip(app_names, row)) for row in app_rows]
        catalog_rows = [dict(zip(catalog_names, row)) for row in catalog_rows]
        task_rows = [dict(zip(task_names, row)) for row in task_rows]

        encrypted_items = []
        for row in item_rows:
            try:
                item_name = row.get("item_name")
                quantity = row.get("quantity")
                encrypted_name = encrypt_text(item_name)
                encrypted_quantity = encrypt_number(quantity)
                if decrypt_text(encrypted_name) != item_name or decrypt_number(encrypted_quantity) != Decimal(str(quantity)):
                    raise ValueError("Round-trip mismatch")
                encrypted_items.append((
                    row["id"], row["application_id"], encrypted_name.encode("ascii"),
                    encrypted_quantity.encode("ascii"), row.get("unit") or "",
                    row.get("created_at") or datetime.utcnow().isoformat(" "),
                    row.get("updated_at") or datetime.utcnow().isoformat(" "),
                ))
            except Exception as exc:
                logger.error("Phase 1e input item round-trip failed for row id %s.", row.get("id"))
                raise RuntimeError(f"Phase 1e migration aborted at input item id {row.get('id')}; no plaintext was removed.") from exc
        counts["input_items"] = len(encrypted_items)

        encrypted_apps = []
        for row in app_rows:
            note = row.get("note")
            try:
                encrypted_note = encrypt_text(note).encode("ascii") if note is not None else None
                if note is not None and decrypt_text(encrypted_note) != note:
                    raise ValueError("Round-trip mismatch")
                encrypted_apps.append((
                    row["id"], row["cycle_id"], row["applied_date"], row.get("category") or "",
                    encrypted_note, row.get("created_at") or datetime.utcnow().isoformat(" "),
                    row.get("updated_at") or datetime.utcnow().isoformat(" "), row.get("deleted_at"),
                ))
            except Exception as exc:
                logger.error("Phase 1e application note round-trip failed for row id %s.", row.get("id"))
                raise RuntimeError(f"Phase 1e migration aborted at input application id {row.get('id')}; no plaintext was removed.") from exc
        counts["applications"] = sum(row[4] is not None for row in encrypted_apps)

        catalog_groups: dict[str, list[dict]] = {}
        for row in catalog_rows:
            normalized_hash = hash_catalog_name(row["item_name"])
            catalog_groups.setdefault(normalized_hash, []).append(row)
        encrypted_catalog = []
        for name_hash, group in catalog_groups.items():
            latest = max(group, key=lambda row: row.get("last_used_at") or "")
            name = (latest.get("item_name") or "").strip()
            encrypted_name = encrypt_text(name)
            try:
                if decrypt_text(encrypted_name) != name:
                    raise ValueError("Round-trip mismatch")
            except Exception as exc:
                logger.error("Phase 1e catalog-name round-trip failed for row id %s.", latest.get("id"))
                raise RuntimeError(f"Phase 1e migration aborted at input catalog id {latest.get('id')}; no plaintext was removed.") from exc
            encrypted_catalog.append((
                min(row["id"] for row in group), encrypted_name.encode("ascii"), name_hash,
                latest.get("last_unit"), latest.get("last_category"), latest.get("last_used_at"),
                sum(row.get("use_count") or 0 for row in group),
            ))
        counts["catalog"] = len(catalog_rows)

        encrypted_tasks = []
        for row in task_rows:
            title = row["title"]
            is_encrypted = bool(row.get("is_encrypted", 0))
            if row.get("source") == "manual" and not is_encrypted:
                try:
                    token = encrypt_text(title)
                    if decrypt_text(token) != title:
                        raise ValueError("Round-trip mismatch")
                    title = token
                    is_encrypted = True
                except Exception as exc:
                    logger.error("Phase 1e manual task title round-trip failed for task id %s.", row.get("id"))
                    raise RuntimeError(f"Phase 1e migration aborted at manual task id {row.get('id')}; no plaintext was removed.") from exc
                counts["tasks"] += 1
            encrypted_tasks.append((
                row["id"], row.get("cycle_id"), title, row["due_date"], row.get("status") or "pending",
                row.get("source") or "manual", row.get("created_at") or datetime.utcnow().isoformat(" "),
                row.get("updated_at") or datetime.utcnow().isoformat(" "), row.get("deleted_at"), int(is_encrypted),
            ))

        connection.execute("""CREATE TABLE input_applications_phase1e (
            id INTEGER NOT NULL PRIMARY KEY, cycle_id INTEGER NOT NULL REFERENCES crop_cycles(id),
            applied_date DATE NOT NULL, category VARCHAR(80) NOT NULL DEFAULT '', note_encrypted BLOB,
            created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL, deleted_at DATETIME
        )""")
        connection.executemany("INSERT INTO input_applications_phase1e VALUES (?, ?, ?, ?, ?, ?, ?, ?)", encrypted_apps)
        connection.execute("""CREATE TABLE input_items_phase1e (
            id INTEGER NOT NULL PRIMARY KEY, application_id INTEGER NOT NULL REFERENCES input_applications_phase1e(id),
            item_name_encrypted BLOB NOT NULL, quantity_encrypted BLOB NOT NULL, unit VARCHAR(80) NOT NULL DEFAULT '',
            created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL
        )""")
        connection.executemany("INSERT INTO input_items_phase1e VALUES (?, ?, ?, ?, ?, ?, ?)", encrypted_items)
        connection.execute("""CREATE TABLE input_catalog_phase1e (
            id INTEGER NOT NULL PRIMARY KEY, name_encrypted BLOB NOT NULL, name_hash VARCHAR(64) NOT NULL UNIQUE,
            last_unit VARCHAR(80), last_category VARCHAR(80), last_used_at DATETIME, use_count INTEGER NOT NULL DEFAULT 0
        )""")
        connection.executemany("INSERT INTO input_catalog_phase1e VALUES (?, ?, ?, ?, ?, ?, ?)", encrypted_catalog)
        connection.execute("""CREATE TABLE tasks_phase1e (
            id INTEGER NOT NULL PRIMARY KEY, cycle_id INTEGER REFERENCES crop_cycles(id) ON DELETE CASCADE,
            title TEXT NOT NULL, due_date DATE NOT NULL, status VARCHAR(20) NOT NULL DEFAULT 'pending',
            source VARCHAR(20) NOT NULL DEFAULT 'manual', created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL, deleted_at DATETIME, is_encrypted BOOLEAN NOT NULL DEFAULT 0
        )""")
        connection.executemany("INSERT INTO tasks_phase1e VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", encrypted_tasks)

        for table in ("input_items", "input_applications", "input_catalog", "tasks"):
            connection.execute(f"DROP TABLE {table}")
        connection.execute("ALTER TABLE input_applications_phase1e RENAME TO input_applications")
        connection.execute("ALTER TABLE input_items_phase1e RENAME TO input_items")
        connection.execute("ALTER TABLE input_catalog_phase1e RENAME TO input_catalog")
        connection.execute("ALTER TABLE tasks_phase1e RENAME TO tasks")
        connection.execute("CREATE INDEX ix_input_items_application_id ON input_items(application_id)")
        connection.execute("CREATE INDEX ix_input_applications_cycle_id ON input_applications(cycle_id)")
        connection.execute("CREATE INDEX ix_input_applications_deleted_at ON input_applications(deleted_at)")
        connection.execute("CREATE UNIQUE INDEX ix_input_catalog_name_hash ON input_catalog(name_hash)")
        connection.execute("CREATE INDEX ix_tasks_cycle_id ON tasks(cycle_id)")
        connection.execute("CREATE INDEX ix_tasks_due_date ON tasks(due_date)")
        connection.execute("CREATE INDEX ix_tasks_status ON tasks(status)")
        connection.execute("CREATE INDEX ix_tasks_deleted_at ON tasks(deleted_at)")
        violations = connection.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise RuntimeError("Phase 1e migration failed foreign-key validation; changes were rolled back.")
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.execute("PRAGMA foreign_keys = ON")
        raw_connection.close()

    _vacuum_sqlite_database(engine, force=True)
    with engine.connect() as verify_connection:
        integrity = verify_connection.exec_driver_sql("PRAGMA integrity_check").scalar()
    if integrity != "ok":
        raise RuntimeError("Phase 1e migration completed but SQLite integrity_check failed.")
    logger.info(
        "Phase 1e migration encrypted %s input items, %s application notes, %s manual tasks, and consolidated %s catalog rows.",
        counts["input_items"], counts["applications"], counts["tasks"], counts["catalog"],
    )
    return counts
