import logging
import os
import sqlite3
import subprocess
from datetime import date, timedelta
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
    if "activities" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("activities")}
    additions = {
        "labor_cost_encrypted": "BLOB",
        "worker_count": "INTEGER",
        "extra_cost_encrypted": "BLOB",
        "stock_alert_product_id": "INTEGER REFERENCES products(id) ON DELETE SET NULL",
    }
    with engine.begin() as connection:
        for name, column_type in additions.items():
            if name not in columns:
                connection.execute(text(f"ALTER TABLE activities ADD COLUMN {name} {column_type}"))
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_activities_open_stock_alert "
            "ON activities(stock_alert_product_id) "
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
            cycle_id = connection.scalar(text("SELECT cycle_id FROM activities WHERE id = :task_id"), {"task_id": task_id}) if task_id else None
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
            "cleaning": "harvested",
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
        "activities": {"updated_at": "TIMESTAMP", "deleted_at": "TIMESTAMP"},
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
    required = {"input_applications", "input_items", "input_catalog", "activities"}
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
        "is_encrypted" not in columns["activities"],
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
        task_rows = connection.execute("SELECT * FROM activities ORDER BY id").fetchall()
        item_names = [row[1] for row in connection.execute("PRAGMA table_info(input_items)")]
        app_names = [row[1] for row in connection.execute("PRAGMA table_info(input_applications)")]
        catalog_names = [row[1] for row in connection.execute("PRAGMA table_info(input_catalog)")]
        task_names = [row[1] for row in connection.execute("PRAGMA table_info(activities)")]
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
        connection.execute("""CREATE TABLE activities_phase1e (
            id INTEGER NOT NULL PRIMARY KEY, cycle_id INTEGER REFERENCES crop_cycles(id) ON DELETE CASCADE,
            title TEXT NOT NULL, due_date DATE NOT NULL, status VARCHAR(20) NOT NULL DEFAULT 'pending',
            source VARCHAR(20) NOT NULL DEFAULT 'manual', created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL, deleted_at DATETIME, is_encrypted BOOLEAN NOT NULL DEFAULT 0
        )""")
        connection.executemany("INSERT INTO activities_phase1e VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", encrypted_tasks)

        for table in ("input_items", "input_applications", "input_catalog", "activities"):
            connection.execute(f"DROP TABLE {table}")
        connection.execute("ALTER TABLE input_applications_phase1e RENAME TO input_applications")
        connection.execute("ALTER TABLE input_items_phase1e RENAME TO input_items")
        connection.execute("ALTER TABLE input_catalog_phase1e RENAME TO input_catalog")
        connection.execute("ALTER TABLE activities_phase1e RENAME TO activities")
        connection.execute("CREATE INDEX ix_input_items_application_id ON input_items(application_id)")
        connection.execute("CREATE INDEX ix_input_applications_cycle_id ON input_applications(cycle_id)")
        connection.execute("CREATE INDEX ix_input_applications_deleted_at ON input_applications(deleted_at)")
        connection.execute("CREATE UNIQUE INDEX ix_input_catalog_name_hash ON input_catalog(name_hash)")
        connection.execute("CREATE INDEX ix_activities_cycle_id ON activities(cycle_id)")
        connection.execute("CREATE INDEX ix_activities_due_date ON activities(due_date)")
        connection.execute("CREATE INDEX ix_activities_status ON activities(status)")
        connection.execute("CREATE INDEX ix_activities_deleted_at ON activities(deleted_at)")
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


_ACTIVITY_COLUMNS = {
    "kind": "VARCHAR(24) NOT NULL DEFAULT 'general'",
    "started_on": "DATE",
    "done_on": "DATE",
    "remind": "BOOLEAN NOT NULL DEFAULT 0",
    "note_encrypted": "BLOB",
    "labor_cost_encrypted": "BLOB",
    "worker_count": "INTEGER",
    "extra_cost_encrypted": "BLOB",
    "stock_alert_product_id": "INTEGER REFERENCES products(id) ON DELETE SET NULL",
    "legacy_input_application_id": "INTEGER",
}

# Titles the stage generator used before activities had a kind.
_LEGACY_STAGE_TITLES = (
    ("ย้ายปลูก", "transplant"),
    ("เตรียมเก็บเกี่ยว", "harvest"),
    ("ทำความสะอาดโต๊ะ", "cleanup"),
)


def migrate_rename_tasks_to_activities(engine: Engine) -> None:
    """Rename the legacy tasks table before anything creates an empty activities table.

    SQLite 3.26+ rewrites foreign keys in other tables that point at the renamed table.
    """
    tables = set(inspect(engine).get_table_names())
    if "tasks" not in tables or "activities" in tables:
        return
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE tasks RENAME TO activities"))
    logger.info("Renamed table tasks to activities.")


def migrate_activities(engine: Engine) -> None:
    """Bring a renamed tasks table up to the activities schema and add the farm-planning columns."""
    from .models import Activity

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if "activities" not in tables:
        return

    with engine.begin() as connection:
        columns = {column["name"] for column in inspect(connection).get_columns("activities")}
        if "due_date" in columns and "planned_date" not in columns:
            connection.execute(text("ALTER TABLE activities RENAME COLUMN due_date TO planned_date"))
        for name, column_type in _ACTIVITY_COLUMNS.items():
            if name not in columns:
                connection.execute(text(f"ALTER TABLE activities ADD COLUMN {name} {column_type}"))

        # Indexes named after the old table are replaced by the model's indexes.
        legacy_indexes = connection.execute(text(
            "SELECT name FROM sqlite_master WHERE type = 'index' AND tbl_name = 'activities' "
            "AND (name LIKE 'ix_tasks_%' OR name LIKE 'uq_tasks_%' OR name = 'ix_activities_due_date')"
        )).scalars().all()
        for name in legacy_indexes:
            connection.execute(text(f'DROP INDEX "{name}"'))
        for index in Activity.__table__.indexes:
            index.create(connection, checkfirst=True)

        _backfill_activity_kinds(connection)

        cycle_columns = {column["name"] for column in inspect(connection).get_columns("crop_cycles")} if "crop_cycles" in tables else set()
        for name, column_type in {
            "seed_count": "INTEGER",
            "plant_count": "INTEGER",
            "expected_transplant_on": "DATE",
            "expected_ready_on": "DATE",
        }.items():
            if cycle_columns and name not in cycle_columns:
                connection.execute(text(f"ALTER TABLE crop_cycles ADD COLUMN {name} {column_type}"))

        if "crop_types" in tables:
            crop_type_columns = {column["name"] for column in inspect(connection).get_columns("crop_types")}
            if "seed_product_id" not in crop_type_columns:
                connection.execute(text(
                    "ALTER TABLE crop_types ADD COLUMN seed_product_id INTEGER REFERENCES products(id) ON DELETE SET NULL"
                ))

        if "tables" in tables:
            table_columns = {column["name"] for column in inspect(connection).get_columns("tables")}
            if "capacity_plants" not in table_columns:
                connection.execute(text("ALTER TABLE tables ADD COLUMN capacity_plants INTEGER NOT NULL DEFAULT 200"))


def _backfill_activity_kinds(connection) -> None:
    """Give activities created before kinds existed the kind their origin implies."""
    connection.execute(text(
        "UPDATE activities SET kind = 'stock_alert' "
        "WHERE kind = 'general' AND stock_alert_product_id IS NOT NULL"
    ))
    if inspect(connection).has_table("sales_order_lines"):
        connection.execute(text(
            "UPDATE activities SET kind = 'order_planting' WHERE kind = 'general' "
            "AND id IN (SELECT planting_task_id FROM sales_order_lines WHERE planting_task_id IS NOT NULL)"
        ))
    for prefix, kind in _LEGACY_STAGE_TITLES:
        connection.execute(text(
            "UPDATE activities SET kind = :kind WHERE kind = 'general' AND source = 'auto' "
            "AND is_encrypted = 0 AND cycle_id IS NOT NULL AND title LIKE :pattern"
        ), {"kind": kind, "pattern": f"{prefix}%"})


# Words in an old input category that mean spraying rather than feeding.
_SPRAY_WORDS = ("ยา", "สาร", "ฉีด", "พ่น", "chemical", "spray", "pest", "insect", "fung", "herb")


def _input_kind(category: str | None) -> str:
    text_value = (category or "").casefold()
    return "spray" if any(word in text_value for word in _SPRAY_WORDS) else "fertilize"


def migrate_activity_records(engine: Engine) -> dict[str, int]:
    """Phase 3 step 2: activities cover crop cycles through targets, and absorb input applications.

    Runs once per row: targets are added only where an activity has none, and each input
    application is converted only if no activity remembers it. Stock movements of a converted
    application are moved over to its activity, so balances do not change.
    """
    counts = {"targets": 0, "done_dates": 0, "applications": 0, "items": 0, "movements": 0}
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if "activities" not in tables or "activity_targets" not in tables:
        return counts

    with engine.begin() as connection:
        if "finance_entries" in tables:
            index_sql = connection.execute(text(
                "SELECT sql FROM sqlite_master WHERE type = 'index' AND name = 'uq_finance_entries_auto_posted_source'"
            )).scalar()
            if index_sql is None or "coalesce" not in index_sql.casefold():
                connection.execute(text("DROP INDEX IF EXISTS uq_finance_entries_auto_posted_source"))
                connection.execute(text(
                    "CREATE UNIQUE INDEX uq_finance_entries_auto_posted_source "
                    "ON finance_entries (source_type, source_id, coalesce(crop_cycle_id, 0)) "
                    "WHERE is_auto = 1 AND status = 'posted' AND source_id IS NOT NULL"
                ))

        counts["done_dates"] = connection.execute(text(
            "UPDATE activities SET done_on = planned_date, started_on = COALESCE(started_on, planned_date) "
            "WHERE status = 'done' AND done_on IS NULL"
        )).rowcount or 0

        counts["targets"] = connection.execute(text("""
            INSERT INTO activity_targets (activity_id, crop_cycle_id, table_id, share, share_is_manual, created_at, updated_at)
            SELECT activity.id, cycle.id, cycle.table_id, 1.0, 0, COALESCE(activity.created_at, CURRENT_TIMESTAMP),
                   COALESCE(activity.updated_at, CURRENT_TIMESTAMP)
            FROM activities AS activity
            JOIN crop_cycles AS cycle ON cycle.id = activity.cycle_id
            WHERE NOT EXISTS (SELECT 1 FROM activity_targets AS target WHERE target.activity_id = activity.id)
        """)).rowcount or 0

        if "input_applications" not in tables or "input_items" not in tables:
            return counts
        applications = connection.execute(text("""
            SELECT application.*, cycle.table_id AS table_id
            FROM input_applications AS application
            LEFT JOIN crop_cycles AS cycle ON cycle.id = application.cycle_id
            WHERE NOT EXISTS (
                SELECT 1 FROM activities WHERE activities.legacy_input_application_id = application.id
            )
            ORDER BY application.id
        """)).mappings().all()
        for application in applications:
            kind = _input_kind(application["category"])
            title = (application["category"] or "").strip() or ("ฉีดพ่น" if kind == "spray" else "ใส่ปุ๋ย")
            created_at = application["created_at"] or datetime.now()
            updated_at = application["updated_at"] or created_at
            activity_id = connection.execute(text("""
                INSERT INTO activities (
                    kind, cycle_id, title, planned_date, started_on, done_on, status, source, remind,
                    is_encrypted, note_encrypted, legacy_input_application_id, created_at, updated_at, deleted_at
                ) VALUES (
                    :kind, :cycle_id, :title, :day, :day, :day, 'done', 'manual', 0,
                    1, :note, :legacy_id, :created_at, :updated_at, :deleted_at
                )
            """), {
                "kind": kind,
                "cycle_id": application["cycle_id"],
                "title": encrypt_text(title),
                "day": application["applied_date"],
                "note": application["note_encrypted"],
                "legacy_id": application["id"],
                "created_at": created_at,
                "updated_at": updated_at,
                "deleted_at": application["deleted_at"],
            }).lastrowid
            if application["table_id"] is not None:
                connection.execute(text(
                    "INSERT INTO activity_targets (activity_id, crop_cycle_id, table_id, share, share_is_manual, created_at, updated_at) "
                    "VALUES (:activity_id, :cycle_id, :table_id, 1.0, 0, :created_at, :updated_at)"
                ), {
                    "activity_id": activity_id, "cycle_id": application["cycle_id"], "table_id": application["table_id"],
                    "created_at": created_at, "updated_at": updated_at,
                })
            items = connection.execute(text(
                "SELECT * FROM input_items WHERE application_id = :application_id ORDER BY id"
            ), {"application_id": application["id"]}).mappings().all()
            for item in items:
                connection.execute(text(
                    "INSERT INTO activity_items (activity_id, item_name_encrypted, product_id, quantity_encrypted, unit, created_at, updated_at) "
                    "VALUES (:activity_id, :name, :product_id, :quantity, :unit, :created_at, :updated_at)"
                ), {
                    "activity_id": activity_id,
                    "name": item["item_name_encrypted"],
                    "product_id": item.get("product_id"),
                    "quantity": item["quantity_encrypted"],
                    "unit": item["unit"] or "",
                    "created_at": item["created_at"] or created_at,
                    "updated_at": item["updated_at"] or updated_at,
                })
                counts["items"] += 1
            if "stock_movements" in tables:
                counts["movements"] += connection.execute(text(
                    "UPDATE stock_movements SET source_type = 'activity', source_id = :activity_id "
                    "WHERE source_type = 'input_application' AND source_id = :application_id"
                ), {"activity_id": activity_id, "application_id": application["id"]}).rowcount or 0
            counts["applications"] += 1

    if any(counts.values()):
        logger.info(
            "Activity records: %s targets, %s finish dates, %s input applications (%s items, %s stock movements) converted.",
            counts["targets"], counts["done_dates"], counts["applications"], counts["items"], counts["movements"],
        )
    return counts


def _as_date(value):
    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def migrate_production_records(engine: Engine) -> dict[str, int]:
    """Phase 3 step 3: harvest entries, expected stage dates, and no more 'empty' cycles.

    - A cycle's single harvest figure becomes one harvest entry; its stock receipt and
      fresh-produce lot follow, so expiry overrides and waste stay attached.
    - An 'empty' cycle was harvested and its table cleaned: it becomes 'harvested' with a
      finished cleanup activity, since tables are now free once cleaned.
    - Cycles without expected dates get them from their crop type.
    """
    counts = {"entries": 0, "movements": 0, "lot_keys": 0, "emptied": 0, "expected": 0}
    tables = set(inspect(engine).get_table_names())
    if not {"crop_cycles", "harvest_entries", "activities", "activity_targets"} <= tables:
        return counts

    with engine.begin() as connection:
        # 1. Single harvest figures become entries.
        cycles = connection.execute(text("""
            SELECT cycle.id, cycle.harvest_quantity_kg, cycle.harvest_date, cycle.updated_at, cycle.nursery_start
            FROM crop_cycles AS cycle
            WHERE cycle.harvest_quantity_kg > 0
              AND NOT EXISTS (SELECT 1 FROM harvest_entries AS entry WHERE entry.crop_cycle_id = cycle.id)
        """)).mappings().all()
        for cycle in cycles:
            harvested_on = _as_date(cycle["harvest_date"]) or _as_date(cycle["updated_at"]) or _as_date(cycle["nursery_start"])
            activity_id = connection.execute(text("""
                SELECT activity.id FROM activities AS activity
                JOIN activity_targets AS target ON target.activity_id = activity.id
                WHERE target.crop_cycle_id = :cycle_id AND activity.kind = 'harvest' AND activity.deleted_at IS NULL
                ORDER BY activity.id LIMIT 1
            """), {"cycle_id": cycle["id"]}).scalar()
            entry_id = connection.execute(text(
                "INSERT INTO harvest_entries (activity_id, crop_cycle_id, harvested_on, quantity_kg, created_at, updated_at) "
                "VALUES (:activity_id, :cycle_id, :harvested_on, :quantity, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ), {
                "activity_id": activity_id, "cycle_id": cycle["id"],
                "harvested_on": harvested_on, "quantity": cycle["harvest_quantity_kg"],
            }).lastrowid
            counts["entries"] += 1
            if "stock_movements" in tables:
                counts["movements"] += connection.execute(text(
                    "UPDATE stock_movements SET source_type = 'harvest_entry', source_id = :entry_id "
                    "WHERE source_type = 'crop_cycle_harvest' AND source_id = :cycle_id AND voided_at IS NULL"
                ), {"entry_id": entry_id, "cycle_id": cycle["id"]}).rowcount or 0
            for table_name in ("lot_expiry_overrides", "stock_waste"):
                if table_name in tables:
                    counts["lot_keys"] += connection.execute(text(
                        f"UPDATE {table_name} SET lot_key = :new_key WHERE lot_key = :old_key"
                    ), {"new_key": f"harvest-entry-{entry_id}", "old_key": f"harvest-{cycle['id']}"}).rowcount or 0

        # 2. 'empty' cycles: harvested, and their table cleaned.
        empty = connection.execute(text(
            "SELECT cycle.id, cycle.table_id, cycle.harvest_date, cycle.updated_at, cycle.nursery_start, "
            "tables.table_number FROM crop_cycles AS cycle LEFT JOIN tables ON tables.id = cycle.table_id "
            "WHERE cycle.status = 'empty'"
        )).mappings().all()
        for cycle in empty:
            cleaned_on = _as_date(cycle["updated_at"]) or _as_date(cycle["harvest_date"]) or _as_date(cycle["nursery_start"])
            connection.execute(text("UPDATE crop_cycles SET status = 'harvested' WHERE id = :id"), {"id": cycle["id"]})
            cleanup_id = connection.execute(text("""
                SELECT activity.id FROM activities AS activity
                JOIN activity_targets AS target ON target.activity_id = activity.id
                WHERE target.crop_cycle_id = :cycle_id AND activity.kind = 'cleanup' AND activity.deleted_at IS NULL
                ORDER BY activity.id LIMIT 1
            """), {"cycle_id": cycle["id"]}).scalar()
            table_label = cycle["table_number"] if cycle["table_number"] is not None else ""
            if cleanup_id is None:
                cleanup_id = connection.execute(text("""
                    INSERT INTO activities (kind, cycle_id, title, planned_date, started_on, done_on, status, source,
                                            remind, is_encrypted, created_at, updated_at)
                    VALUES ('cleanup', :cycle_id, :title, :day, :day, :day, 'done', 'auto', 0, 0,
                            CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """), {"cycle_id": cycle["id"], "title": f"ทำความสะอาดโต๊ะ {table_label}".strip(),
                       "day": cleaned_on}).lastrowid
                connection.execute(text(
                    "INSERT INTO activity_targets (activity_id, crop_cycle_id, table_id, share, share_is_manual, created_at, updated_at) "
                    "VALUES (:activity_id, :cycle_id, :table_id, 1.0, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                ), {"activity_id": cleanup_id, "cycle_id": cycle["id"], "table_id": cycle["table_id"]})
            else:
                connection.execute(text(
                    "UPDATE activities SET status = 'done', done_on = COALESCE(done_on, :day), "
                    "started_on = COALESCE(started_on, :day) WHERE id = :id"
                ), {"id": cleanup_id, "day": cleaned_on})
            connection.execute(text(
                "INSERT INTO crop_cycle_status_logs (cycle_id, from_status, to_status, changed_at) "
                "VALUES (:cycle_id, 'empty', 'harvested', CURRENT_TIMESTAMP)"
            ), {"cycle_id": cycle["id"]})
            counts["emptied"] += 1

        # 3. Expected stage dates.
        missing = connection.execute(text("""
            SELECT cycle.id, cycle.nursery_start, cycle.transplant_date, cycle.expected_transplant_on, cycle.expected_ready_on,
                   crop.nursery_days, crop.growth_days
            FROM crop_cycles AS cycle JOIN crop_types AS crop ON crop.id = cycle.crop_type_id
            WHERE cycle.expected_transplant_on IS NULL OR cycle.expected_ready_on IS NULL
        """)).mappings().all()
        for cycle in missing:
            transplant_on = _as_date(cycle["expected_transplant_on"]) or (
                _as_date(cycle["nursery_start"]) + timedelta(days=cycle["nursery_days"])
            )
            ready_on = _as_date(cycle["expected_ready_on"]) or (
                (_as_date(cycle["transplant_date"]) or transplant_on) + timedelta(days=cycle["growth_days"])
            )
            connection.execute(text(
                "UPDATE crop_cycles SET expected_transplant_on = :transplant_on, expected_ready_on = :ready_on WHERE id = :id"
            ), {"transplant_on": transplant_on, "ready_on": ready_on, "id": cycle["id"]})
            counts["expected"] += 1

    if any(counts.values()):
        logger.info(
            "Production records: %s harvest entries (%s stock movements, %s lot keys), %s empty cycles closed, %s expected dates.",
            counts["entries"], counts["movements"], counts["lot_keys"], counts["emptied"], counts["expected"],
        )
    return counts
