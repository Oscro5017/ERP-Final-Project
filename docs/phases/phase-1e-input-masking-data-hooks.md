# Phase 1e: Input Masking and Data Hooks

Status: implementation and live migration complete. The full task prompt is archived at [Project-Phase/erp-farm-phase1e-input-masking-data-hooks-prompt.md](../../Project-Phase/erp-farm-phase1e-input-masking-data-hooks-prompt.md).

## Scope

Part A encrypts input item names and numeric quantities, application notes, catalog names, and manually entered task titles. Fernet tokens are stored in SQLite. Owner responses decrypt values; developer responses return ciphertext with `is_masked: true`. Catalog matching uses a normalized name and a keyed HMAC-SHA256 derived from `ENCRYPTION_KEY`; developers receive no catalog suggestions. Automatic lifecycle tasks remain plaintext and their generator is unchanged.

The SQLite migration creates a restricted backup outside the repository, validates round trips before replacing legacy tables, consolidates normalized catalog duplicates, removes old plaintext columns, vacuums the database, and checks SQLite integrity. A failed validation rolls back the migration.

Part B adds:

- `ForecastSnapshot`, uniquely keyed by issue date, target date, and source, populated daily from the existing forecast service.
- A background startup catch-up that fills missing `WeatherLog` dates from the preceding 14 days without blocking API startup.
- `SensorReading` and `POST`/`GET /sensors/readings`; writes require `X-Device-Token` and reads require JWT.
- An empty `Recommendation` model only. No recommendation rules, API, or UI are part of this phase.

## Security Boundary

These controls protect data exposed through application APIs and screens. A person with shell access to the host and `ENCRYPTION_KEY` can decrypt the database. Production keys must be controlled by the farm owner and backed up separately from the database.

## Acceptance

- Owner can read and search their input records and manual task titles; developer sees ciphertext or a neutral encrypted-data label.
- Legacy plaintext input columns are absent after migration, and old values round-trip from the encrypted columns.
- Forecast snapshots are upserted; catch-up tolerates per-day weather failures.
- Sensor writes reject missing/invalid device credentials, unsupported or out-of-range values, and timestamps too far in the future; duplicate readings update rather than duplicate.
- Backend tests and frontend production build pass.

## Phase 2 Coordination

Phase 2 context previously proposed an `Insight` table and `/insights`; this phase adds `Recommendation` as an empty data hook. Before Phase 2 implementation, reconcile both names into one resource and do not create duplicate tables or endpoints. No Phase 2 spec was present in the workspace during Phase 1e implementation.
