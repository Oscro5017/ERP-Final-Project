# Phase 2 report

## 0. PASTE-BACK SUMMARY (ก๊อปส่วนนี้ส่งกลับ)

PHASE2 REPORT | วันที่รัน: 2026-11-24 | branch: backend/products-stock
TEST: คำสั่ง=Remove-Item Env:ENCRYPTION_KEY -ErrorAction SilentlyContinue; .\.venv\Scripts\python.exe -m pytest -q -o faulthandler_timeout=60 | passed=229 failed=0 skipped=0 warnings=73 (73.48s) | baseline ก่อนเริ่ม=96 passed, 73 warnings | เทสต์เดิมที่ถูกแก้/ลบ=0
VERIFIED/UNVERIFIED: read endpoints × unauth/owner/developer, write route auth + owner/developer response flows, marker scan ใน DB/log, populated synthetic Phase 1e + Slice 1b migrations รันซ้ำ=VERIFIED; actual farm backup migration และ perf smoke บนเครื่องเป้าหมาย=UNVERIFIED/ผู้ใช้ต้องรันเอง

SLICES: 2.0=DONE 2.1=DONE 2.2a=DONE 2.2b=DONE 2.3a=DONE 2.3b=DONE 2.3c=DONE 2.3d=DONE 2.4a=DONE 2.4b=DONE 2.4c=DONE 2.5=DONE 2.6=DONE

SCHEMA: ตารางใหม่=Supplier, StockDocument, StockDocumentLine, FinanceEntry, Insight | คอลัมน์เพิ่มแบบ nullable=CropType.product_id, InputItem.product_id, InputCatalog.product_id, Customer.area_encrypted, Task.labor_cost_encrypted, Task.extra_cost_encrypted, Task.worker_count, Task.stock_alert_product_id | migrations additive/idempotent; full synthetic populated Phase 1e + Slice 1b DB migration test ผ่าน 2 รอบ
ENDPOINTS ใหม่: กลุ่ม Products/Suppliers/Trade/Stock/Crop mapping/Inputs/Finance/Tasks/Dashboard/Insights; รายการใน docs/API_PHASE2.md และ docs/openapi.phase2.json
DEPENDENCY ใหม่: ไม่มีรายงาน dependency ใหม่

DEVIATIONS:
- แนวทางช่วงต้น StockReceipt/StockIssue และ /stock/receipts|issues ถูกแทนด้วย StockDocument/StockDocumentLine และ /trade/* ตาม PJP2; ค้น app code, routers, migrations และ tests แล้วไม่พบชื่อหรือเส้นทางเก่า; ข้อความในรายงาน/บันทึกนี้เป็นประวัติเท่านั้น.
ASSUMPTIONS:
- ใช้ CropType.product_id เป็น mapping; ใช้ Product.reorder_point ที่มีอยู่; ไม่มี Sale/Order/Invoice เดิม; ชื่อ supplier ซ้ำเตือนแต่ไม่บล็อก; เพิ่มตาราง products/stock ก่อน canary เพราะ FK ใหม่.
BLOCKERS: ไม่พบตัวขวางการส่งมอบ backend; ไม่มีการใช้ DB จริงหรือ dev ในการตรวจนี้.
BUG/ความเสี่ยง: ยังไม่มีผล performance smoke 2,000 รายการบนเครื่องเป้าหมาย; ยังไม่ได้ลอง migration กับสำเนา farm backup จริง.
ไฟล์นอกขอบเขตที่เปลี่ยนอยู่: frontend/ และ src/ มี dirty files ซึ่ง baseline บันทึกว่ามีอยู่ก่อน Phase 2; ห้ามรวมโดยเผลอ stage.
PERF SMOKE: สคริปต์พร้อมที่ `scripts/phase2_perf_smoke.py`; ไม่ได้รันตามที่กำหนดให้ผู้ใช้วัดบนเครื่องเป้าหมาย. รันด้วย `Remove-Item Env:ENCRYPTION_KEY -ErrorAction SilentlyContinue; .\.venv\Scripts\python.exe -m scripts.phase2_perf_smoke`.

เก็บตกที่ผู้ใช้ต้องทำเอง:
- [ ] ทบทวนรายงานและแยกไฟล์ frontend ที่ค้างก่อน commit; ยังไม่มี commit/push/เปลี่ยน branch.
- [ ] รันสคริปต์ performance บน Pi/เครื่องเป้าหมายและส่งผลเวลา summary/dashboard.
- [ ] ทดสอบ migration ด้วยสำเนาฐานจริงและ key ที่ตรงกับข้อมูลสำรอง; ห้ามใช้ key dev กับข้อมูลจริง.
คำถามที่ต้องให้เจ้าของฟาร์ม/ผู้ร่วมงานตัดสิน: ยืนยันนโยบายชั่วคราวเรื่องเข้ารหัสชื่อสินค้าและพื้นที่กับเจ้าของฟาร์มก่อนใช้งานจริง.

## 1. ตารางสถานะรายสไลซ์

| Slice | สถานะ | เทสต์ใหม่/หลักฐาน | หมายเหตุ |
|---|---|---|---|
| 2.0 | DONE | baseline บันทึกใน PHASE2_BASELINE.md | baseline hash manifest เดิมไม่มี; สถานะ pre-work ถอดจาก session output |
| 2.1 | DONE | 37 trade tests, suite 133 passed | StockDocument, Supplier, /trade/* |
| 2.2a | DONE | 15 tests, suite 148 passed | harvest to stock |
| 2.2b | DONE | 12 tests, suite 160 passed | input deductions |
| 2.3a | DONE | 26 tests, suite 186 passed | finance ledger and reports |
| 2.3b | DONE | 8 tests + migration coverage, suite 194 passed | Task costs |
| 2.3c | DONE | 7 tests, suite 201 passed | price and customer reports |
| 2.3d | DONE | 4 tests, suite 216 passed | encrypted Customer area |
| 2.4a | DONE | 8 tests, suite 209 passed at that point | balances and movement reads |
| 2.4b | DONE | 3 tests, suite 212 passed | dashboard |
| 2.4c | DONE | 3 tests total, suite 217 passed at completion; two dedicated no-duplicate/re-cross tests added in final audit | low-stock reminders |
| 2.5 | DONE | 4 tests, suite 221 passed | unified Insight migration/API |
| 2.6 | DONE | e2e test, final suite 222 passed | OpenAPI/API docs and hardening |

## 2. หลักฐานการทดสอบ

วันที่ 2026-11-24 รัน PowerShell โดยลบ ENCRYPTION_KEY ออกจาก process ก่อนใช้ Python ใน .venv: `Remove-Item Env:ENCRYPTION_KEY -ErrorAction SilentlyContinue; .\.venv\Scripts\python.exe -m pytest -q -o faulthandler_timeout=60` ผลสุดท้าย `229 passed, 73 warnings in 73.48s`; failed=0, skipped=0. Baseline คือ 96 passed, 73 warnings. ไม่มีการแก้หรือลบเทสต์เดิม; เพิ่มไฟล์เทสต์ใหม่.

Cross-cutting ตาม 02-TEST-PLAN หมวด B:
- Masking/auth matrix: ทุก Phase 2 read endpoint ทดสอบ unauthenticated/owner/developer; write routes ทดสอบ unauthenticated และ owner/developer flows สำหรับ response-bearing mutations. Marker assertion ผ่าน.
- ไม่มี plaintext ใน DB: marker scan ทุกตารางใน populated fixture และหลัง create/update/void flows ผ่าน; encrypted fields เริ่มต้น Fernet token.
- ไม่ log plaintext: caplog ระหว่าง create/update/void/report flows ไม่พบ markers หรือจำนวนเงินทดสอบ.
- Atomicity: มี rollback tests สำหรับเอกสาร, harvest และ input hook; ไม่พบหลักฐานครบทุก flow ที่แตะ stock+finance.
- Idempotency: มี tests สำหรับ harvest, migration/Insight copy, retry/void และ hook บางส่วน; ไม่ใช่ cross-cutting suite ครบทุกกรณี.
- Soft delete/void ในรายงาน: มีกรณีเฉพาะฟีเจอร์; ไม่มี test matrix รวม.
- Migration DB เก่า: สร้าง populated Phase 1e + Slice 1b schema โดยไม่มี Phase 2 tables/columns, รัน Phase 2 migrations 2 รอบ, ตรวจ encrypted legacy data/stock balance/recommendation copy คงเดิม; ผ่าน. ยังไม่ได้ใช้ farm backup จริง.
- Production startup: `tests/test_encryption_canary.py` มี production lifespan mismatched-canary rejection tests (test_production_lifespan_refuses_mismatched_canary; test_production_lifespan_rejects_mismatched_canary_before_scheduler); รวมอยู่ใน full suite.
- Regression: 96 baseline tests ยังไม่ถูกแก้/ลบตาม tracked diff; full suite ผ่าน.
- Performance 2,000 rows: มีสคริปต์ temp SQLite ที่วัด median/max เวลา summary/dashboard; ไม่ได้รันเพื่อให้ผู้ใช้วัดบนเครื่องเป้าหมาย.

## 3. การเปลี่ยนแปลงโครงสร้างข้อมูล

เพิ่ม Supplier, StockDocument, StockDocumentLine, FinanceEntry และ Insight. เพิ่ม nullable mappings บน CropType/InputItem/InputCatalog; encrypted area บน Customer; encrypted labor/extra costs, worker_count และ stock alert link บน Task. ตาราง Product/StockMovement เป็นฐาน Slice 1. ข้อมูลที่เข้ารหัสตาม policy ถูกเก็บเป็น encrypted fields; stock quantities/balances เปิดตามสัญญา. Migration entry points อยู่ใน app/migrations.py และถูกเรียกจาก startup. มี migration tests แบบ additive/idempotent รายส่วน; ยังไม่มีหลักฐานรันกับสำเนาฐาน legacy เต็มชุด. ไม่มีแผน rollback migration ที่ทำลายข้อมูล; การย้อนกลับต้องใช้ backup/restore และยังไม่ผ่านการซ้อม.

## 4. API ที่เพิ่ม

รายการเต็มและ schemas อยู่ใน docs/API_PHASE2.md และ docs/openapi.phase2.json. เพิ่ม/ขยายกลุ่ม products, suppliers, trade inbound/outbound/documents, stock balances/movements, crop product mapping, input product mappings, finance entries/summary/P&L/prices/customer revenue, task costs, dashboard summary และ insights. ทุก endpoint ใหม่ต้อง auth; owner อ่านค่าถอดรหัส ส่วน developer ได้ข้อมูล masked/ciphertext ตาม policy.

## 5. การตัดสินใจ / ข้อสันนิษฐาน / ส่วนที่เบี่ยงจาก spec

- จุดสำคัญ: mapping ผลผลิตใช้ nullable unique CropType.product_id (หนึ่ง crop type ต่อสินค้า); mapping เดิมยังว่างจนผู้ใช้ตั้ง.
- ใช้ Product.reorder_point ที่มีอยู่แทนการเพิ่ม reorder_level ซ้ำ.
- ใช้ unified StockDocument/StockDocumentLine และ /trade/* ตาม PJP2 แทนดีไซน์แยกรับเข้า/จ่ายออกช่วงต้น; ตรวจ git grep แล้วไม่พบ identifier/path เก่าภายใน app/tests/docs.
- Supplier ชื่อซ้ำเป็นคำเตือน ไม่บล็อก; ไม่มี Sale/Order/Invoice model เดิมจึงไม่สร้างซ้ำ.
- สร้างตาราง products/stock ก่อน encryption preflight เพื่อให้ foreign key จาก CropType ใช้ได้; production mismatch rejection tests มีอยู่และผ่านใน full suite.

## 6. ความเสี่ยงและบั๊กที่พบ

- ไม่มี pre-work hash manifest; baseline historical git status สร้างจาก output ของ session ตามที่บันทึกใน PHASE2_BASELINE.md.
- มีไฟล์ frontend/src ที่ dirty อยู่ก่อนงาน Phase 2 และยังค้าง ห้าม stage รวมกับ backend.
- Performance smoke บน Pi/เครื่องเป้าหมาย และ migration rehearsal บนสำเนา farm backup ยังค้าง.
- Synthetic migration test สร้าง legacy schema จาก current model definitions แล้วปรับให้ตรง Phase 1e/Slice 1b; ไม่ได้ตรวจฐานสำรองจริง.
- ยังไม่มีการ deploy หรือเปิดฐาน production; เทสต์เป็น local/temp DB.

## 7. ลำดับ git ที่แนะนำ (ผู้ใช้ทำเอง)

ยังไม่แนะนำให้ commit แบบ `git add .` เพราะ frontend dirty และ baseline manifest ไม่ครบ. ตรวจ `git status --short` และทบทวนทีละไฟล์ก่อน; แยก backend/API/migrations/tests/docs Phase 2 ออกจาก frontend/src และไฟล์ที่มีอยู่ก่อนเริ่ม. หากต้องการ commits ราย slice ให้เลือกไฟล์ร่วมของแต่ละ slice จาก diff จริงและหลีกเลี่ยงการ stage ไฟล์รวมข้าม slice; เก็บ frontend changes ไว้ commit แยกตามเจตนาของผู้ใช้. ไม่มี commit, push, merge หรือ branch switch ในงานนี้.

## 8. เก็บตกที่เหลือ (OPEN ITEMS)

1. (M) ผู้ใช้รัน performance smoke บนเครื่องเป้าหมาย (2,000 finance rows) และบันทึกเวลา.
2. (M) ผู้ใช้ rehearsal migration ด้วยสำเนา farm backup จริง; ห้ามเปิดฐานจริง.
3. (S) พิจารณาเพิ่ม failure-injection atomicity matrix ครบทุก stock+finance flow; ฟีเจอร์หลักมี rollback tests แต่ยังไม่มี suite รวม.
4. (S) แยกสถานะไฟล์ frontend ก่อนจัด commit.
5. (S) ส่งรายงานฉบับอัปเดตให้ Claude หลังทบทวนเนื้อหา.

## 9. เสนอขั้นต่อไป

1. ให้ผู้ใช้/ที่ปรึกษาทบทวน PASTE-BACK SUMMARY และผลเก็บตก.
2. รัน perf smoke และ migration rehearsal บนสำเนาฐานจริง.
3. วางแผน commit backend Phase 2 โดยกันไฟล์ frontend ที่ค้างออก.
4. เชื่อม UI เว็บ/มือถือกับ API หลังยืนยันรูปแบบ client.
5. ก่อนใช้งานจริง ให้เจ้าของฟาร์มยืนยัน masking policy ชั่วคราวและเตรียม backup/key production.

