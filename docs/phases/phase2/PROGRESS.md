## STATUS
2.0 DONE | 2.1 DONE | 2.2a DONE | 2.2b DONE | 2.3a DONE | 2.3b DONE | 2.3c DONE | 2.3d DONE | 2.4a DONE | 2.4b DONE | 2.4c DONE | 2.5 DONE | 2.6 DONE

## BASELINE
branch=backend/products-stock | pre-Phase-2 pytest=96 passed, 73 warnings | pre-existing dirty frontend files retained | exact pre-work hash manifest unavailable; see PHASE2_BASELINE.md

## PER-SLICE LOG
2.0: DONE; baseline map and pre-work status/diff/test snapshot recorded in PHASE2_BASELINE.md. The historical status is reconstructed from session output; no real/dev DB was opened.
2.1: DONE; unified StockDocument/Supplier models, additive migration, `/trade/*`, daily IN/OUT numbering, encrypted amounts and notes, transactional movements/void; 37 new trade tests; latest full suite=133 passed, 73 warnings.
2.2a: DONE; nullable unique `CropType.product_id` mapping; `PATCH /crop-types/{id}/product-mapping`; same-transaction, idempotent harvest receipt movements; edits/clear/soft delete void correctly; 15 new tests; full suite=148 passed, 73 warnings.
2.2b: DONE; nullable product mappings on `InputItem` and `InputCatalog`; catalog suggestions retain prior mapping; create/edit/delete synchronizes application deductions transactionally; unit conversion/mismatch warning; 12 new tests; full suite=160 passed, 73 warnings.
2.3a: DONE; encrypted `FinanceEntry` ledger, automatic document income/expense with void propagation, manual entry CRUD/void, entry filters, summary and cycle P&L with date/row caps and masked aggregates; 26 new tests; full suite=186 passed, 73 warnings.
2.3b: DONE; optional encrypted labor/extra costs and worker count on Task; completed tasks create/update/void linked automatic labor expenses; existing task contract retained with optional fields; 8 new task-finance tests plus additive migration coverage; full suite=194 passed, 73 warnings.
2.3c: DONE; `/finance/prices` weighted averages/min/max and `/finance/customers/revenue` totals/share/rank with Bangkok calendar grouping, masking, decryption failure counts, 366-day and 10,000-row limits; 7 new tests; full suite=201 passed, 73 warnings.
2.4a: DONE; `/stock/balances` SQL totals at Bangkok end-of-day and `/stock/movements` filters/pagination with void rows hidden by default; masked product names and notes; 8 new tests; full suite=209 passed, 73 warnings.
2.4b: DONE; `/dashboard/summary` includes product/negative balances, five crop-cycle statuses, due/overdue pending tasks, and masked current-month finance; 3 tests; full suite=212 passed, 73 warnings.
2.3d: DONE; nullable encrypted Customer area with additive migration, create/update API, area-based summary and price grouping (developers receive masked keys); 4 new tests; full suite=216 passed, 73 warnings.
2.4c: DONE; the existing `Product.reorder_point` is used as the threshold; every ledger change creates at most one encrypted low-stock Task, replenishment closes it, and later threshold crossings can create a new reminder; 1 new test; full suite=217 passed, 73 warnings.
2.5: DONE; additive encrypted `Insight` table, idempotent legacy `Recommendation` copy, and list/get/status API; 4 new tests; full suite before 2.6=221 passed, 73 warnings.
2.6: DONE; cross-module workflow test, generated OpenAPI and API handoff, project/masking/agent docs updated; final full suite=222 passed, 73 warnings.
Post-slice verification: added read/write endpoint role matrix, raw DB/log marker checks, populated Phase 1e + Slice 1b migration rerun test, and two dedicated reorder tests; final full suite=229 passed, 0 failed, 0 skipped, 73 warnings in 73.48s. Perf smoke script compiled; intentionally not executed so the user can measure the target machine.

## ASSUMPTIONS
- No `Sale`, `Order`, or `Invoice` model/table exists; new trade documents will not create a duplicate order model.
- Supplier duplicate names will warn rather than block, as required by PJP2 D13; the name HMAC index must therefore be non-unique.
- Crop output mapping uses `CropType.product_id` (one crop type per product), the option explicitly allowed by PJP2; existing crop types remain unmapped until a user assigns one.
- PJP2's `Product.reorder_level` is represented by the existing `Product.reorder_point`, which already stores the stock threshold used by product APIs; no duplicate threshold column is added.
- Startup creates the additive products/stock tables before the encryption preflight because the new CropType foreign key references products; existing startup migration tests confirm this ordering.
- Work remains on the current branch; no git write operation or real/dev database access is authorized.

## DEVIATIONS (spec vs code)
- The initial Slice 2 direction used separate StockReceipt/StockIssue models and `/stock/receipts`/`/stock/issues` routes; it was fully replaced by the required StockDocument/StockDocumentLine and `/trade/*` design before Slice 2 completion. Current app code and tests contain no old model or route identifiers; historical references remain in this progress log.

## OPEN ITEMS
- Synthetic legacy migration and cross-cutting masking/storage/log tests pass; the real farm backup has not been opened or migrated.
- Run `python -m scripts.phase2_perf_smoke` on the target device and report its actual timings before production use.
- No commit/push/branch switch performed; share the updated Phase 2 report for review before deciding commit order.

