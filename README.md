# Organic Farm ERP

FastAPI + SQLAlchemy backend with a React/Vite dashboard for a hydroponic farm.

The React source is kept in `src/` and the production bundle is built into
`frontend/`, which is served by FastAPI. The original `code_prototype` folder
remains separate for UI comparison.

## Run locally (development)

1. Create a virtual environment and install dependencies:
   `python -m venv .venv` then `.venv\Scripts\pip install -r requirements.txt`
2. Copy `.env.example` to `.env` and set `ENCRYPTION_KEY` to a generated Fernet key.
3. Start the API: `uvicorn app.main:app --reload`
4. Open http://127.0.0.1:8000 or http://127.0.0.1:8000/docs.

Development mode keeps the API docs enabled and seeds the sample accounts
`owner / owner123` and `developer / developer123`. Do not use these credentials
or development secrets in production.

## Raspberry Pi deployment

Use one Uvicorn worker because each worker starts its own weather scheduler.
Do not use `--reload` on the Pi.
Scheduled weather jobs retry once with a short backoff. A
follow-up catch-up runs 30 minutes later and fills missing weather history
within the latest 14 days; any dates still unavailable are retried on the next
daily catch-up. Scheduler outcomes and failures are written to the service log.
Weather UI requests use a 3-second upstream timeout; scheduled sync, snapshot,
and catch-up jobs use 15 seconds and retry once. Empty successful forecasts are
cached for 30 seconds (capped at 60); non-empty results use the configured
`WEATHER_FORECAST_CACHE_SECONDS`.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
# Edit .env: set APP_ENV=production, strong JWT_SECRET, ENCRYPTION_KEY,
# BACKUP_DIR outside the repository, CORS_ORIGINS, and initial account passwords.
# PASSWORD_HASH_ITERATIONS defaults to 120000; raise it only after measuring login time on the Pi.
# For Cloudflare Tunnel, set TRUSTED_PROXY_IPS to the direct tunnel peer only
# (for example 127.0.0.1/32 only when cloudflared connects over loopback).
# LOG_LEVEL defaults to INFO; LOG_DIR defaults to logs/ for rotating app logs.
.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
```

Login throttling trusts `CF-Connecting-IP` only when the direct peer matches
`TRUSTED_PROXY_IPS`; otherwise it keys attempts by the direct peer address.
Failures receive progressive backoff from 1 second up to 60 seconds.

When a production database has no owner/developer accounts, set
`INITIAL_OWNER_PASSWORD` and `INITIAL_DEVELOPER_PASSWORD` before the first
startup. The application does not log those values. Migrations that require a
backup stop if `BACKUP_DIR` is unset; backup files may contain plaintext data,
so keep the directory private and outside the Git repository. Production API
docs are disabled unless `ENABLE_DOCS=true` is explicitly set.

Before deploying SQLite foreign-key enforcement to an existing database, run
this read-only audit on the Pi. It makes a temporary SQLite backup copy,
reports only table names and violation counts, and never repairs rows:

```bash
.venv/bin/python -m scripts.check_sqlite_foreign_keys /home/pi/erp-app/erp.db
```

If it reports violations, stop and review those relationships before restarting
the service with the new backend.

To audit encrypted fields with the key configured in `.env`, run the checker
from the application directory. It opens the database read-only and prints only
counts, row IDs, error types, and token-format labels:

```bash
.venv/bin/python -m scripts.check_decrypt /home/pi/erp-app/erp.db
```

To refresh historical weather-model rows that may contain old fallback values,
choose an explicit date range and run this script manually. It overwrites only
dates with a complete upstream response; it was not run as part of this code
change:

```bash
.venv/bin/python -m scripts.resync_weather_history 2026-10-17 2026-11-01
```

Run backend tests with:

```bash
python -m venv .venv
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
# macOS/Linux
source .venv/bin/activate
pip install -r requirements.txt
python -m pytest -q
```

To rebuild the dashboard after frontend changes:

1. `npm install`
2. `npm run build`

The Vite development server is available with `npm run dev` on port 3000 and
proxies API requests to the FastAPI server on port 8000.

The browser stores the JWT in localStorage for this prototype only. Customer names are always encrypted in SQLite. Owners receive decrypted names; developers receive a compact customer ID instead of the encrypted value.
