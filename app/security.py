import hashlib
import hmac
import base64
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from .config import get_settings
from .database import get_db
from .models import Role, User

bearer = HTTPBearer(auto_error=False)


PASSWORD_HASH_SCHEME = "pbkdf2_sha256"
PASSWORD_HASH_ITERATIONS = 120_000


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PASSWORD_HASH_ITERATIONS)
    encoded_salt = base64.urlsafe_b64encode(salt).decode("ascii").rstrip("=")
    return f"{PASSWORD_HASH_SCHEME}${PASSWORD_HASH_ITERATIONS}${encoded_salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    if stored.startswith(f"{PASSWORD_HASH_SCHEME}$"):
        try:
            scheme, iterations, encoded_salt, expected = stored.split("$", 3)
            salt = base64.urlsafe_b64decode(encoded_salt + "=" * (-len(encoded_salt) % 4))
            actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, int(iterations)).hex()
        except (ValueError, TypeError):
            return False
        return scheme == PASSWORD_HASH_SCHEME and hmac.compare_digest(actual, expected)

    try:
        salt, expected = stored.split("$", 1)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120_000).hex()
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


def password_hash_needs_upgrade(stored: str) -> bool:
    return not stored.startswith(f"{PASSWORD_HASH_SCHEME}$")


def create_access_token(user: User) -> str:
    settings = get_settings()
    expires = datetime.now(UTC) + timedelta(minutes=settings.jwt_expire_minutes)
    return jwt.encode({"sub": str(user.id), "role": user.role.value, "exp": expires}, settings.jwt_secret, algorithm="HS256")


def get_current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)) -> User:
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    try:
        payload = jwt.decode(credentials.credentials, get_settings().jwt_secret, algorithms=["HS256"])
        user_id = int(payload.get("sub", ""))
    except (JWTError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


def get_current_role(user: User = Depends(get_current_user)) -> Role:
    return user.role
