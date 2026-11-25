# Phase 2 baseline

Captured 2026-11-24 from branch `backend/products-stock`. The pre-Phase-2 test run recorded in this session was `96 passed, 73 warnings`; command: `.\.venv\Scripts\python.exe -m pytest -q -o faulthandler_timeout=60`, after clearing `ENCRYPTION_KEY` from the process.

## Working tree at the pre-Slice-2 snapshot

`git status --short` already contained changes in `.gitignore`, the Phase 1/Slice 1 backend and policy files, and React build/UI files under `frontend/` and `src/`; the Slice 1 prompt and `Run.md` were untracked. The frontend changes were present before Phase 2 work and are not to be reverted. The recorded tracked diff summary was 14 files changed, 200 insertions, 30,787 deletions; most deletions were generated frontend assets.

## Code map

| Area | Current code |
|---|---|
| Product / stock ledger | `Product` and `StockMovement`: `app/models.py:130`, `app/models.py:145`; endpoints `app/routers/products.py`; service `app/services/products_stock.py` (`record_movement` flushes only; stock totals use SQL SUM). |
| Customer | `Customer`: `app/models.py:108`; endpoints `app/routers/customers.py`. |
| Crop type / cycle | `CropType` (`name`, nursery/growth days): `app/models.py:65`, reference router `app/routers/reference.py`; `CropCycle` (`crop_type_id`, dates, status, `harvest_quantity_kg`): `app/models.py:73`, cycle endpoints `app/routers/crop_cycles.py`; `CropCycleStatusLog`: `app/models.py:92`. |
| Inputs | `InputApplication` / `InputItem`: `app/models.py:222`, `app/models.py:234`; API `app/routers/input_applications.py`; `InputCatalog`: `app/models.py:115`, helper `app/services/input_catalog.py`. |
| Task | `Task` (`cycle_id`, title, due_date, status, source, `is_encrypted`): `app/models.py:255`; API `app/routers/tasks.py`. |
| Insight / recommendation | No `Insight` model found; `Recommendation` (`kind`, title/message/reason, window, status, task_id) exists at `app/models.py:307`. |
| Sensors | `SensorReading` (`device_id`, type/value/unit, recorded/received timestamps): `app/models.py:298`; API `app/routers/sensors.py`. |
| Migrations | Custom idempotent/additive entry points include `migrate_system_meta`, `migrate_products_stock`, customer/crop/Phase 1c/Phase 1e migrations in `app/migrations.py`; startup order is in `app/main.py:lifespan`. |
| Test DB / API auth | No root `conftest.py` found; temp SQLite setup is local to tests (for example `tests/test_products_stock.py:20`). `get_db` is `app/database.py:37`; role dependency is `app/security.py:69`. |
| Encryption | `safe_decrypt_text`, `present_number_safe`, `encrypt_number`, `present_aggregate`, and HMAC name helpers are in `app/services/secure_fields.py`. |

No `Sale`, `Order`, or `Invoice` model/table was found in `app/models.py` or the routers/services searched. `PROJECT_CONTEXT.md` and `PROJECT_STATUS.md` are present.

## Baseline limitations

The pre-Phase-2 branch/status/test snapshot is reconstructed from the captured session output. The exact pre-work file hash manifest was not captured. No real or development database was opened for this baseline.
