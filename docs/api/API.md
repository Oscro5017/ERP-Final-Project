# API

All routes require authentication. Owner responses decrypt protected fields; developer responses return ciphertext and `is_masked`. Both roles may write, following the existing Phase 1 policy. Request and response schemas are in `openapi.json` (rebuild with `python -m scripts.export_openapi` from `backend/`).

| Area | Endpoints | Protected response fields |
|---|---|---|
| Products | `/products` CRUD, `/products/{id}/adjustments`, `/products/{id}/movements` | Product name, movement note |
| Suppliers | `/suppliers` CRUD | Name, contact, area, note |
| Trade | `POST /trade/inbound`, `POST /trade/outbound`, `GET/PATCH /trade/documents`, `POST /trade/documents/{id}/void` | Supplier/customer names, notes, prices, amounts, void reason |
| Stock | `GET /stock/balances`, `GET /stock/movements` | Product name, movement note; balances and quantities remain open |
| Tables | `GET /tables`, `GET /tables/board`, `PATCH /tables/{id}` (plant capacity) | None |
| Crop types | `GET /crop-types`, `PATCH /crop-types/{id}` (stage days, seed item), `PATCH /crop-types/{id}/product-mapping` | Product name remains masked under product policy |
| Crop cycles | CRUD, `POST /crop-cycles/{id}/status`, `GET/POST /crop-cycles/{id}/harvests`, `DELETE /crop-cycles/harvests/{entry_id}`, `/status-log`, `/changes` | Change-note values and reasons |
| Activities | `/activities` CRUD, `POST /activities/{id}/status`, `GET /activities/{id}/changes`, `/input-catalog/suggestions` | Titles, notes, item names and quantities, labor/extra costs, change notes |
| Tasks (old pages) | `/tasks` CRUD, the same activities seen the old way | Manual titles and labor/extra costs |
| Notifications | `GET /notifications`, `POST /notifications/{id}/read`, `POST /notifications/read-all`, `POST /push-devices`, `POST /push-devices/remove` | Reminder title and body (owner only) |
| Finance | `GET/POST /finance/entries`, `PATCH /finance/entries/{id}`, `POST /finance/entries/{id}/void`, `GET /finance/summary`, `/finance/cycles/{id}/pnl`, `/finance/prices`, `/finance/customers/revenue` | Amounts and aggregates; customer names/areas |
| Dashboard | `GET /dashboard/summary` | Finance totals |
| Insights | `GET /insights`, `GET /insights/{id}`, `PATCH /insights/{id}/status` | Title and body |

## Activities drive the records

- An activity is `pending` (planned, with a reminder), `in_progress` or `done`. Only a done activity takes its stock-linked items out of stock (on `done_on`) and turns its labor and extra cost into expenses.
- One activity may cover several crop cycles or tables. Its cost is split across cycles by plant count unless the owner fixes a share.
- Editing an activity recomputes stock and expenses and leaves change notes; `reason` is optional.
- Starting a crop cycle with `seed_count` records a done nursery activity that takes the crop type's seed item (counted in seeds).
- Stages: `nursery → bushed → ready_to_harvest → harvesting → harvested`. A cycle becomes ready on `expected_ready_on` through a daily job. Each harvest entry enters stock on its own day as its own fresh lot; the final entry closes the harvest.
- A harvested cycle keeps its table space until a cleanup activity is done.

Finance aggregation is decrypted in Python, limited to a 366-day range and 10,000 rows; responses report skipped decrypt failures and truncation.
