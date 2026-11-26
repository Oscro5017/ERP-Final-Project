import hashlib

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import Base, Role, User
from app.security import hash_password, password_hash_needs_upgrade, verify_password


TEST_FERNET_KEY = "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="


def test_password_hashes_use_independent_random_salts():
    first = hash_password("same-test-password")
    second = hash_password("same-test-password")
    assert first.startswith("pbkdf2_sha256$120000$")
    assert first != second
    assert verify_password("same-test-password", first)
    assert not verify_password("wrong-password", first)
    assert not password_hash_needs_upgrade(first)


def test_legacy_password_hash_verifies_and_is_marked_for_upgrade():
    password = "legacy-test-password"
    salt = hashlib.sha256(password.encode()).hexdigest()[:32]
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120_000).hex()
    legacy_hash = f"{salt}${digest}"
    assert verify_password(password, legacy_hash)
    assert password_hash_needs_upgrade(legacy_hash)


@pytest.mark.parametrize("overrides", [
    {"jwt_secret": "change-this-in-production"},
    {"jwt_secret": "short"},
    {"jwt_secret": "s" * 32, "device_token": "too-short"},
    {"jwt_secret": "s" * 32, "cors_origins": "*"},
])
def test_production_rejects_weak_secrets_and_wildcard_cors(overrides):
    values = {"_env_file": None, "encryption_key": TEST_FERNET_KEY, "app_env": "production"}
    values.update(overrides)
    with pytest.raises(ValueError):
        Settings(**values)


def test_password_hash_iteration_setting_rejects_values_below_minimum():
    with pytest.raises(ValueError):
        Settings(_env_file=None, encryption_key=TEST_FERNET_KEY, password_hash_iterations=99_999)


def test_new_password_hash_uses_configured_iterations(monkeypatch):
    from app import security

    monkeypatch.setattr(
        security,
        "get_settings",
        lambda: type("Settings", (), {"password_hash_iterations": 123_456})(),
    )
    assert security.hash_password("synthetic-password").startswith("pbkdf2_sha256$123456$")


def test_production_accepts_strong_secrets_and_disables_docs_by_default():
    settings = Settings(
        _env_file=None, encryption_key=TEST_FERNET_KEY, app_env="production",
        jwt_secret="j" * 48, device_token="d" * 32,
    )
    assert settings.docs_enabled is False
    assert Settings(_env_file=None, encryption_key=TEST_FERNET_KEY).docs_enabled is True
    assert Settings(
        _env_file=None, encryption_key=TEST_FERNET_KEY, app_env="production", enable_docs=True,
        jwt_secret="j" * 48,
    ).docs_enabled is True


def test_env_example_defaults_parse_without_real_secrets():
    settings = Settings(_env_file=".env.example", encryption_key=TEST_FERNET_KEY)
    assert settings.app_env == "development"
    assert settings.docs_enabled is True
    assert settings.backup_dir is None
    assert settings.initial_owner_password is None
    assert settings.initial_developer_password is None
    assert settings.scheduler_misfire_grace_seconds == 21_600
    assert settings.weather_forecast_cache_seconds == 900


def test_api_docs_routes_follow_environment():
    from app.main import create_app

    production = Settings(
        _env_file=None, encryption_key=TEST_FERNET_KEY, app_env="production", jwt_secret="j" * 48,
    )
    development = Settings(_env_file=None, encryption_key=TEST_FERNET_KEY)
    production_routes = {route.path for route in create_app(production).routes}
    development_routes = {route.path for route in create_app(development).routes}
    assert "/docs" not in production_routes
    assert "/redoc" not in production_routes
    assert "/openapi.json" not in production_routes
    assert {"/docs", "/redoc", "/openapi.json"} <= development_routes


def test_weather_page_refresh_serves_spa_without_swallowing_api_404s(tmp_path):
    from fastapi.testclient import TestClient

    from app.main import create_app

    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<!doctype html><title>ERP</title>", encoding="utf-8")
    settings = Settings(_env_file=None, encryption_key=TEST_FERNET_KEY, frontend_dir=str(tmp_path))
    client = TestClient(create_app(settings))

    page_response = client.get("/weather")
    trailing_slash_response = client.get("/weather/")
    unknown_api_response = client.get("/weather/unknown")
    api_route_response = client.get("/weather/history")

    assert page_response.status_code == 200
    assert trailing_slash_response.status_code == 200
    assert "text/html" in page_response.headers["content-type"]
    assert unknown_api_response.status_code == 404
    assert api_route_response.status_code == 401


def test_api_starts_before_the_web_app_is_built(tmp_path):
    from fastapi.testclient import TestClient

    from app.main import create_app

    settings = Settings(_env_file=None, encryption_key=TEST_FERNET_KEY, frontend_dir=str(tmp_path / "missing"))
    client = TestClient(create_app(settings))
    assert client.get("/weather").status_code == 404
    assert client.get("/weather/history").status_code == 401


def test_relative_runtime_paths_start_at_project_root():
    from app.config import PROJECT_ROOT

    settings = Settings(_env_file=None, encryption_key=TEST_FERNET_KEY, database_url="sqlite:///./erp.db", log_dir="logs")
    assert settings.database_url == "sqlite:///" + (PROJECT_ROOT / "erp.db").as_posix()
    assert settings.log_dir == str(PROJECT_ROOT / "logs")
    assert Settings(_env_file=None, encryption_key=TEST_FERNET_KEY, database_url="sqlite://").database_url == "sqlite://"


def test_login_failure_lockout_and_expiry(monkeypatch):
    from app.routers import auth

    auth.reset_login_attempts()
    now = [100.0]
    monkeypatch.setattr(auth.time, "monotonic", lambda: now[0])
    key = auth._login_key("owner", "192.0.2.1")
    assert not auth._is_login_locked(key)
    for _ in range(auth._LOGIN_FAILURE_LIMIT):
        auth._record_login_failure(key)
    assert auth._is_login_locked(key)
    assert not auth._is_login_locked(auth._login_key("owner", "192.0.2.2"))
    now[0] += auth._LOGIN_LOCK_SECONDS + 1
    assert not auth._is_login_locked(key)


def test_successful_legacy_login_upgrades_hash(monkeypatch):
    from starlette.requests import Request

    from app import security
    from app.routers import auth

    legacy_password = "legacy-login-password"
    salt = hashlib.sha256(legacy_password.encode()).hexdigest()[:32]
    digest = hashlib.pbkdf2_hmac("sha256", legacy_password.encode(), salt.encode(), 120_000).hex()
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        user = User(username="legacy-login-owner", password_hash=f"{salt}${digest}", role=Role.owner)
        db.add(user)
        db.commit()
        db.refresh(user)
        request = Request({"type": "http", "client": ("192.0.2.50", 1234), "headers": []})
        monkeypatch.setattr(security, "get_settings", lambda: type("S", (), {"jwt_secret": "j" * 48, "jwt_expire_minutes": 30})())
        auth.reset_login_attempts()
        response = auth.login(
            type("Payload", (), {"username": user.username, "password": legacy_password})(), request, db
        )
        assert response.access_token
        assert user.password_hash.startswith("pbkdf2_sha256$")
    engine.dispose()


def test_successful_login_upgrades_hash_below_configured_iterations(monkeypatch):
    from starlette.requests import Request

    from app import security
    from app.routers import auth

    password = "versioned-lower-rounds-password"
    iterations = 100_000
    salt = b"synthetic-salt-123"
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations).hex()
    encoded_salt = __import__("base64").urlsafe_b64encode(salt).decode("ascii").rstrip("=")
    old_hash = f"pbkdf2_sha256${iterations}${encoded_salt}${digest}"
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        user = User(username="lower-rounds-owner", password_hash=old_hash, role=Role.owner)
        db.add(user)
        db.commit()
        db.refresh(user)
        request = Request({"type": "http", "client": ("192.0.2.51", 1234), "headers": []})
        monkeypatch.setattr(
            security,
            "get_settings",
            lambda: type("Settings", (), {
                "jwt_secret": "j" * 48,
                "jwt_expire_minutes": 30,
                "password_hash_iterations": 125_000,
            })(),
        )
        auth.reset_login_attempts()
        response = auth.login(
            type("Payload", (), {"username": user.username, "password": password})(), request, db
        )
        assert response.access_token
        assert user.password_hash.startswith("pbkdf2_sha256$125000$")
    engine.dispose()


def test_production_seed_skips_accounts_without_initial_passwords(caplog):
    from app.seed import seed_database

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    settings = Settings(
        _env_file=None, encryption_key=TEST_FERNET_KEY, app_env="production", jwt_secret="j" * 48,
    )
    with Session(engine) as db:
        seed_database(db, settings=settings)
        assert db.scalars(select(User)).all() == []
        assert "Initial owner account was not created" in caplog.text
        assert "Initial developer account was not created" in caplog.text
        assert "owner123" not in caplog.text
    engine.dispose()


def test_development_seed_uses_legacy_default_credentials():
    from app.seed import seed_database

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    settings = Settings(_env_file=None, encryption_key=TEST_FERNET_KEY)
    with Session(engine) as db:
        seed_database(db, settings=settings)
        users = {user.username: user for user in db.scalars(select(User)).all()}
        assert verify_password("owner123", users["owner"].password_hash)
        assert verify_password("developer123", users["developer"].password_hash)
    engine.dispose()


def test_cloudflare_client_ip_is_used_only_for_configured_proxy(monkeypatch):
    from starlette.requests import Request

    from app.routers import auth

    settings = Settings(
        _env_file=None, encryption_key=TEST_FERNET_KEY,
        trusted_proxy_ips="127.0.0.1/32",
    )
    monkeypatch.setattr(auth, "get_settings", lambda: settings)
    trusted_request = Request({
        "type": "http", "client": ("127.0.0.1", 1234),
        "headers": [(b"cf-connecting-ip", b"203.0.113.8")],
    })
    untrusted_request = Request({
        "type": "http", "client": ("192.0.2.10", 1234),
        "headers": [(b"cf-connecting-ip", b"203.0.113.8")],
    })

    assert auth._client_ip(trusted_request) == "203.0.113.8"
    assert auth._client_ip(untrusted_request) == "192.0.2.10"


def test_login_failures_use_progressive_bounded_backoff(monkeypatch):
    from app.routers import auth

    auth.reset_login_attempts()
    now = [100.0]
    monkeypatch.setattr(auth.time, "monotonic", lambda: now[0])
    key = auth._login_key("owner", "192.0.2.9")
    delays = []
    for _ in range(8):
        auth._record_login_failure(key)
        state = auth._LOGIN_FAILURES[key]
        delays.append(state[1] - now[0])
        now[0] = state[1]

    assert delays[:4] == [1, 2, 4, 8]
    assert delays[-1] == auth._LOGIN_BACKOFF_MAX_SECONDS
    assert all(delay <= auth._LOGIN_BACKOFF_MAX_SECONDS for delay in delays)
    auth.reset_login_attempts()


def test_production_startup_rejects_legacy_default_password_before_migration(monkeypatch):
    import asyncio
    from sqlalchemy.orm import sessionmaker

    from app import main

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(User(username="farm_admin", password_hash=hash_password("owner123"), role=Role.owner))
        db.commit()

    settings = Settings(
        _env_file=None, encryption_key=TEST_FERNET_KEY, app_env="production",
        jwt_secret="j" * 48,
    )
    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr(main, "SessionLocal", sessionmaker(bind=engine))
    migration_calls = []
    monkeypatch.setattr(main, "migrate_crop_cycles", lambda _engine: migration_calls.append("migration"))
    api = main.create_app(settings)

    async def start_application():
        async with main.lifespan(api):
            pass

    with pytest.raises(RuntimeError, match="development default password"):
        asyncio.run(start_application())
    assert migration_calls == []
    engine.dispose()
