import base64
import hashlib
import hmac
import logging
import threading
import unicodedata
import time
from collections import OrderedDict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from cryptography.fernet import Fernet
from cryptography.fernet import InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from ..config import get_settings
from ..models import Role

logger = logging.getLogger(__name__)
DECRYPT_FAILED_TEXT = "[ถอดรหัสไม่ได้]"
_DECRYPT_LOG_INTERVAL_SECONDS = 60.0
_DECRYPT_LOG_CACHE_LIMIT = 4096
_DECRYPT_LOG_CACHE: OrderedDict[tuple[str, str, str, str], float] = OrderedDict()
_DECRYPT_LOG_LOCK = threading.Lock()


@dataclass(frozen=True)
class SafeDecryptionResult:
    value: object
    decrypt_failed: bool = False


def _log_decrypt_failure(table: str, row_id: int | str, field: str, error: Exception) -> None:
    error_type = type(error).__name__
    key = (table, str(row_id), field, error_type)
    now = time.monotonic()
    with _DECRYPT_LOG_LOCK:
        previous = _DECRYPT_LOG_CACHE.get(key)
        if previous is not None and now - previous < _DECRYPT_LOG_INTERVAL_SECONDS:
            return
        _DECRYPT_LOG_CACHE[key] = now
        _DECRYPT_LOG_CACHE.move_to_end(key)
        while len(_DECRYPT_LOG_CACHE) > _DECRYPT_LOG_CACHE_LIMIT:
            _DECRYPT_LOG_CACHE.popitem(last=False)

    logger.error(
        "Encrypted field decryption failed table=%s row_id=%s field=%s error_type=%s",
        table,
        row_id,
        field,
        error_type,
        extra={"table": table, "row_id": row_id, "field": field, "error_type": error_type},
    )


def safe_decrypt_text(token: bytes | str, *, table: str, row_id: int | str, field: str) -> SafeDecryptionResult:
    try:
        return SafeDecryptionResult(decrypt_text(token))
    except (InvalidToken, UnicodeError, InvalidOperation, ValueError, TypeError) as exc:
        _log_decrypt_failure(table, row_id, field, exc)
        return SafeDecryptionResult(DECRYPT_FAILED_TEXT, True)


def safe_decrypt_number(token: bytes | str | None, *, table: str, row_id: int | str, field: str) -> SafeDecryptionResult:
    if token is None:
        return SafeDecryptionResult(None)
    try:
        return SafeDecryptionResult(decrypt_number(token))
    except (InvalidToken, UnicodeError, InvalidOperation, ValueError, TypeError) as exc:
        _log_decrypt_failure(table, row_id, field, exc)
        return SafeDecryptionResult(None, True)


def present_text_safe(
    token: bytes | str | None,
    role: Role | str,
    *,
    table: str,
    row_id: int | str,
    field: str,
) -> SafeDecryptionResult:
    if token is None:
        return SafeDecryptionResult("")
    if role == Role.owner or role == Role.owner.value:
        return safe_decrypt_text(token, table=table, row_id=row_id, field=field)
    return SafeDecryptionResult(present_text(token, role))


def present_number_safe(
    token: bytes | str | None,
    role: Role | str,
    *,
    table: str,
    row_id: int | str,
    field: str,
) -> SafeDecryptionResult:
    if role == Role.owner or role == Role.owner.value:
        return safe_decrypt_number(token, table=table, row_id=row_id, field=field)
    if token is None:
        return SafeDecryptionResult(None)
    return SafeDecryptionResult(token.decode("ascii") if isinstance(token, bytes) else token)


def _fernet() -> Fernet:
    return Fernet(get_settings().encryption_key.encode("ascii"))


def normalize_catalog_name(value: str) -> str:
    return unicodedata.normalize("NFC", (value or "").strip()).casefold()


def hash_catalog_name(value: str) -> str:
    key = base64.urlsafe_b64decode(get_settings().encryption_key.encode("ascii"))
    derived_key = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=b"input-catalog-name-hash:v1",
    ).derive(key)
    normalized = normalize_catalog_name(value).encode("utf-8")
    return hmac.new(derived_key, normalized, hashlib.sha256).hexdigest()


def encrypt_text(plain: str) -> str:
    return _fernet().encrypt(plain.encode("utf-8")).decode("ascii")


def decrypt_text(token: bytes | str) -> str:
    if isinstance(token, str):
        token = token.encode("ascii")
    return _fernet().decrypt(token).decode("utf-8")


def present_text(token: bytes | str | None, role: Role | str) -> str:
    if token is None:
        return ""
    if role == Role.owner or role == Role.owner.value:
        return decrypt_text(token)
    if isinstance(token, bytes):
        return token.decode("ascii")
    return token


def encrypt_number(value: Decimal | int | float | str) -> str:
    try:
        number = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("value must be a finite decimal number") from exc
    if not number.is_finite():
        raise ValueError("value must be a finite decimal number")
    return encrypt_text(str(number))


def decrypt_number(token: bytes | str) -> Decimal:
    try:
        number = Decimal(decrypt_text(token))
    except InvalidOperation as exc:
        raise ValueError("encrypted value does not contain a decimal number") from exc
    if not number.is_finite():
        raise ValueError("encrypted value does not contain a finite decimal number")
    return number


def present_number(token: bytes | str, role: Role | str) -> Decimal | str:
    if role == Role.owner or role == Role.owner.value:
        return decrypt_number(token)
    return token.decode("ascii") if isinstance(token, bytes) else token


def present_aggregate(value: Decimal | int | float | str, role: Role | str) -> dict[str, Decimal | str | bool]:
    try:
        number = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("value must be a finite decimal number") from exc
    if not number.is_finite():
        raise ValueError("value must be a finite decimal number")
    if role == Role.owner or role == Role.owner.value:
        return {"value": number, "is_masked": False}
    return {"value": encrypt_text(str(number)), "is_masked": True}
