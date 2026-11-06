import hashlib
import ipaddress
import threading
import time

from fastapi import APIRouter, Depends, HTTPException
from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..models import User
from ..schemas import LoginRequest, TokenResponse
from ..security import create_access_token, hash_password, password_hash_needs_upgrade, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])
_LOGIN_FAILURE_LIMIT = 5
_LOGIN_LOCK_SECONDS = 15 * 60
_LOGIN_BACKOFF_MAX_SECONDS = 60
_LOGIN_FAILURES: dict[tuple[str, str], tuple[int, float, float]] = {}
_LOGIN_FAILURES_LOCK = threading.Lock()
_DUMMY_PASSWORD_HASH = hash_password("invalid-account-password-for-timing-equalization")


def _login_key(username: str, client_ip: str) -> tuple[str, str]:
    username_key = hashlib.sha256(username.casefold().encode("utf-8")).hexdigest()
    return username_key, client_ip


def _client_ip(request: Request) -> str:
    peer_ip = request.client.host if request.client else "unknown"
    try:
        peer_address = ipaddress.ip_address(peer_ip)
    except ValueError:
        return peer_ip

    settings = get_settings()
    for configured_network in getattr(settings, "trusted_proxy_ip_list", []):
        try:
            if peer_address in ipaddress.ip_network(configured_network, strict=False):
                forwarded_ip = request.headers.get("cf-connecting-ip", "").strip()
                try:
                    return ipaddress.ip_address(forwarded_ip).compressed
                except ValueError:
                    return peer_address.compressed
        except ValueError:
            continue
    return peer_address.compressed


def _is_login_locked(key: tuple[str, str], now: float | None = None) -> bool:
    now = time.monotonic() if now is None else now
    with _LOGIN_FAILURES_LOCK:
        for old_key, (failures, locked_until, last_attempt) in list(_LOGIN_FAILURES.items()):
            if last_attempt + _LOGIN_LOCK_SECONDS <= now:
                _LOGIN_FAILURES.pop(old_key, None)
        state = _LOGIN_FAILURES.get(key)
        return bool(state and state[1] > now)


def _record_login_failure(key: tuple[str, str], now: float | None = None) -> None:
    now = time.monotonic() if now is None else now
    with _LOGIN_FAILURES_LOCK:
        failures, locked_until, last_attempt = _LOGIN_FAILURES.get(key, (0, 0.0, 0.0))
        if last_attempt + _LOGIN_LOCK_SECONDS <= now:
            failures = 0
        failures += 1
        delay = min(2 ** (failures - 1), _LOGIN_BACKOFF_MAX_SECONDS)
        _LOGIN_FAILURES[key] = (
            failures,
            now + delay,
            now,
        )


def _clear_login_failures(key: tuple[str, str]) -> None:
    with _LOGIN_FAILURES_LOCK:
        _LOGIN_FAILURES.pop(key, None)


def reset_login_attempts() -> None:
    """Clear in-memory login limiter state (also useful for isolated tests)."""
    with _LOGIN_FAILURES_LOCK:
        _LOGIN_FAILURES.clear()


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    client_ip = _client_ip(request)
    key = _login_key(payload.username, client_ip)
    if _is_login_locked(key):
        raise HTTPException(status_code=401, detail="ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง")

    user = db.scalar(select(User).where(User.username == payload.username))
    stored_hash = user.password_hash if user else _DUMMY_PASSWORD_HASH
    valid_password = verify_password(payload.password, stored_hash)
    if not user or not valid_password:
        _record_login_failure(key)
        raise HTTPException(status_code=401, detail="ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง")

    _clear_login_failures(key)
    if password_hash_needs_upgrade(user.password_hash):
        user.password_hash = hash_password(payload.password)
        db.commit()
    return TokenResponse(access_token=create_access_token(user), role=user.role)
