import logging
from decimal import InvalidOperation

from cryptography.fernet import InvalidToken
from sqlalchemy import inspect, select
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import Session

from ..config import Settings
from ..models import SystemMeta
from .encrypted_data_audit import audit_encrypted_data
from .secure_fields import decrypt_text, encrypt_text

logger = logging.getLogger(__name__)
ENCRYPTION_CANARY_KEY = "encryption_canary"
ENCRYPTION_CANARY_PLAINTEXT = "organic-farm-encryption-canary:v1"


def encryption_canary_status(connection: Connection) -> str:
    if not inspect(connection).has_table(SystemMeta.__tablename__):
        return "ยังไม่มี"

    encrypted_value = connection.scalar(
        select(SystemMeta.value).where(SystemMeta.key == ENCRYPTION_CANARY_KEY)
    )
    if encrypted_value is None:
        return "ยังไม่มี"

    try:
        return "ปกติ" if decrypt_text(encrypted_value) == ENCRYPTION_CANARY_PLAINTEXT else "ไม่ตรง"
    except (InvalidToken, UnicodeError, InvalidOperation, ValueError, TypeError):
        return "ไม่ตรง"


def ensure_encryption_canary(db: Session, engine: Engine, settings: Settings) -> str:
    connection = db.connection()
    status = encryption_canary_status(connection)
    production = settings.app_env.strip().lower() == "production"

    if status == "ปกติ":
        logger.info("Encryption canary verified against the database.")
        return status
    if status == "ไม่ตรง":
        logger.error("Encryption canary mismatch: the configured key does not match this database.")
        if production:
            raise RuntimeError("ENCRYPTION_KEY does not match the database; refusing production startup.")
        return status

    if engine.dialect.name != "sqlite":
        logger.error("Encryption canary not created: encrypted-data preflight currently requires SQLite.")
        if production:
            raise RuntimeError("Could not verify existing encrypted data; refusing production startup.")
        return "ยังไม่มี"

    audits = audit_encrypted_data(connection)
    failed_values = sum(result.fail for result in audits)
    if failed_values:
        logger.error(
            "Encryption canary not created: %s existing encrypted value(s) failed the key preflight.",
            failed_values,
        )
        if production:
            raise RuntimeError("Existing encrypted data failed key preflight; refusing production startup.")
        return "ยังไม่มี"

    db.add(SystemMeta(key=ENCRYPTION_CANARY_KEY, value=encrypt_text(ENCRYPTION_CANARY_PLAINTEXT)))
    try:
        db.commit()
    except Exception:
        db.rollback()
        status = encryption_canary_status(db.connection())
        if status != "ปกติ":
            raise
        logger.info("Encryption canary created by another application worker.")
        return status

    logger.info("Encryption canary created after encrypted-data preflight passed.")
    return "ปกติ"