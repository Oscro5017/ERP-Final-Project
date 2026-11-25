# Phase 2 API

All routes require authentication. Owner responses decrypt protected fields; developer responses return ciphertext and `is_masked`. Both roles may write, following the existing Phase 1 policy.

| Area | Endpoints | Protected response fields |
|---|---|---|
| Products | `/products` CRUD, `/products/{id}/adjustments`, `/products/{id}/movements` | Product name, movement note |
| Suppliers | `/suppliers` CRUD | Name, contact, area, note |
| Trade | `POST /trade/inbound`, `POST /trade/outbound`, `GET/PATCH /trade/documents`, `POST /trade/documents/{id}/void` | Supplier/customer names, notes, prices, amounts, void reason |
| Stock | `GET /stock/balances`, `GET /stock/movements` | Product name, movement note; balances and quantities remain open |
| Crop mapping | `GET /crop-types`, `PATCH /crop-types/{id}/product-mapping`; crop cycle CRUD | Product name remains masked under product policy |
| Inputs | `/crop-cycles/{id}/input-applications`, `/input-applications/{id}` CRUD, `/input-catalog/suggestions` | Input names, quantities, notes |
| Finance | `GET/POST /finance/entries`, `PATCH /finance/entries/{id}`, `POST /finance/entries/{id}/void`, `GET /finance/summary`, `/finance/cycles/{id}/pnl`, `/finance/prices`, `/finance/customers/revenue` | Amounts and aggregates; customer names/areas |
| Tasks | `/tasks` CRUD | Manual titles and labor/extra costs |
| Dashboard | `GET /dashboard/summary` | Finance totals |
| Insights | `GET /insights`, `GET /insights/{id}`, `PATCH /insights/{id}/status` | Title and body |

Finance aggregation is decrypted in Python, limited to a 366-day range and 10,000 rows; responses report skipped decrypt failures and truncation. See `docs/openapi.phase2.json` for request and response schemas.
