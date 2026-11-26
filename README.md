# Organic Farm ERP

ERP for a small hydroponic farm: crop cycles and farm tasks, warehouse stock
(items, fresh produce, inbound and outbound documents), customer orders and
sales, finance, and weather. The farm owner uses it on a phone; a developer
account sees the same data with private fields masked.

## Project layout

```
backend/          FastAPI + SQLAlchemy + SQLite
  app/
    routers/      HTTP endpoints, one file per area
    services/     business rules (stock, orders, finance, planting …)
    schemas/      request and response models, one file per area
    models.py     database tables
    migrations.py upgrades for databases created by older versions
  tests/          pytest suite
  scripts/        maintenance tools (decrypt audit, foreign-key audit, OpenAPI export)
web/              React 19 + Vite + Tailwind
  src/
    pages/        one folder per menu: farm/, warehouse/, sales/, finance/
    components/   shared UI (forms, pickers, dialogs, charts)
    lib/, utils/  API client and helpers
mobile/           Flutter app for the owner
docs/
  api/            endpoint summary and generated OpenAPI schema
  design/         wireframes
  vv/             course verification & validation documents
  MASKING_POLICY.md  which fields are encrypted or masked
```

Runtime files stay at the repository root and are not committed: `.env`,
the SQLite database (`erp.db`), `logs/`, and the built web app in `web/dist/`.
Relative paths in `.env` are read from the repository root, so the backend
finds the same files whether it is started from the root or from `backend/`.

## Run locally (development)

Backend, from the repository root:

```bash
python -m venv .venv
.venv\Scripts\pip install -r backend/requirements.txt      # Windows
# .venv/bin/pip install -r backend/requirements.txt        # macOS/Linux
cp .env.example .env   # then set ENCRYPTION_KEY to a generated Fernet key
.venv\Scripts\python -m uvicorn app.main:app --app-dir backend --reload --reload-dir backend --port 8000
```

Web app, in a second terminal:

```bash
cd web
npm install
npm run dev     # http://localhost:3000, proxies API calls to port 8000
```

API docs are at http://127.0.0.1:8000/docs. Development mode seeds the sample
accounts `owner / owner123` and `developer / developer123`. Do not use these
credentials or development secrets in production.

To let the backend serve the pages itself on port 8000, build the web app once
with `npm run build` in `web/`. Without a build the API still runs and only the
pages are missing.

## Tests

```bash
cd backend
../.venv/Scripts/python -m pytest -q      # Windows
# ../.venv/bin/python -m pytest -q        # macOS/Linux
```

## Raspberry Pi deployment

The built web app is no longer committed, so build it before starting the
service, either on the Pi (`cd web && npm ci && npm run build`) or on another
machine and copy `web/dist/` to the Pi.

```bash
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
cp .env.example .env
# Edit .env: set APP_ENV=production, strong JWT_SECRET, ENCRYPTION_KEY,
# BACKUP_DIR outside the repository, CORS_ORIGINS, and initial account passwords.
# PASSWORD_HASH_ITERATIONS defaults to 120000; raise it only after measuring login time on the Pi.
# For Cloudflare Tunnel, set TRUSTED_PROXY_IPS to the direct tunnel peer only
# (for example 127.0.0.1/32 only when cloudflared connects over loopback).
# LOG_LEVEL defaults to INFO; LOG_DIR defaults to logs/ for rotating app logs.
.venv/bin/python -m uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000 --workers 1
```

Use one Uvicorn worker because each worker starts its own weather scheduler,
and do not use `--reload` on the Pi. Scheduled weather jobs retry once with a
short backoff. A follow-up catch-up runs 30 minutes later and fills missing
weather history within the latest 14 days; dates still unavailable are retried
on the next daily catch-up. Scheduler outcomes and failures are written to the
service log. Weather UI requests use a 3-second upstream timeout; scheduled
sync, snapshot and catch-up jobs use 15 seconds and retry once. Empty successful
forecasts are cached for 30 seconds (capped at 60); non-empty results use the
configured `WEATHER_FORECAST_CACHE_SECONDS`.

Login throttling trusts `CF-Connecting-IP` only when the direct peer matches
`TRUSTED_PROXY_IPS`; otherwise it keys attempts by the direct peer address.
Failures receive progressive backoff from 1 second up to 60 seconds.

When a production database has no owner/developer accounts, set
`INITIAL_OWNER_PASSWORD` and `INITIAL_DEVELOPER_PASSWORD` before the first
startup. The application does not log those values. Migrations that require a
backup stop if `BACKUP_DIR` is unset; backup files may contain plaintext data,
so keep the directory private and outside the Git repository. Production API
docs are disabled unless `ENABLE_DOCS=true` is explicitly set.

### Maintenance scripts

Run these from `backend/`; they read `.env` from the repository root.

Read-only foreign-key audit before enabling SQLite foreign keys on an existing
database. It makes a temporary backup copy, reports only table names and
violation counts, and never repairs rows. If it reports violations, review
those relationships before restarting the service:

```bash
../.venv/bin/python -m scripts.check_sqlite_foreign_keys /home/pi/erp-app/erp.db
```

Read-only audit of encrypted fields with the key in `.env`. It prints only
counts, row IDs, error types and token-format labels:

```bash
../.venv/bin/python -m scripts.check_decrypt /home/pi/erp-app/erp.db
```

Refresh historical weather rows for an explicit date range. It overwrites only
dates with a complete upstream response:

```bash
../.venv/bin/python -m scripts.resync_weather_history 2026-10-17 2026-11-01
```

Regenerate `docs/api/openapi.json` after changing endpoints:

```bash
../.venv/bin/python scripts/export_openapi.py
```

## Security notes

The browser stores the JWT in localStorage for this prototype only. Customer
names and other private fields are always encrypted in SQLite. Owners receive
decrypted values; developers receive masked values instead. See
`docs/MASKING_POLICY.md`.
