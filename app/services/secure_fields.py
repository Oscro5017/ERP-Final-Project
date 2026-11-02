import base64
import hashlib
import hmac
import unicodedata
from decimal import Decimal, InvalidOperation

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from ..config import get_settings
from ..models import Role


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
