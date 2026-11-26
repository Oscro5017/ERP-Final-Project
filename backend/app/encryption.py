import base64

from cryptography.fernet import Fernet

from .config import get_settings


def _fernet() -> Fernet:
    return Fernet(get_settings().encryption_key.encode())


def encrypt_text(value: str) -> bytes:
    return _fernet().encrypt(value.encode())


def decrypt_text(value: bytes) -> str:
    return _fernet().decrypt(value).decode()


def ciphertext_string(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")
