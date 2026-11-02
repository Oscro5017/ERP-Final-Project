# Phase 1e — ปิดบังข้อมูลปุ๋ย/กิจกรรม + เตรียมช่องเก็บข้อมูลสำหรับเซนเซอร์และคำแนะนำ

> อ่าน `PROJECT_CONTEXT.md`, `PROJECT_STATUS.md` และ `Project-Phase/` ที่เกี่ยวข้องก่อนเริ่ม
> ทำ **Part A ให้เสร็จและผ่าน tests ก่อน** แล้วค่อยทำ Part B
> ห้ามเปลี่ยนพฤติกรรมของ Phase 1d (Customer) นอกจากที่ระบุ

> **ข้อกำหนดที่ถูก supersede (2026-11-01):** ส่วน Phase 1e ที่กำหนดให้ `InputItem.quantity` ปิดบังเป็นข้อกำหนดในอดีตเท่านั้น. ให้ยึด `MASKING_POLICY.md`: quantity/stock เปิดสำหรับ developer; ชื่อปุ๋ย/ยา, note และเงินยังปิด. ข้อมูลปัจจุบันยังเข้ารหัส quantity อยู่ จึงต้องทำ decrypt/round-trip migration และ API response change พร้อม D4/product linkage ก่อนเปิดตัวเลข; ห้ามแสดง ciphertext ใน frontend.

## บริบท

- เจ้าของฟาร์มถือว่า **ชนิด ยี่ห้อ และปริมาณที่ผสมของปุ๋ย/ยา** เป็นความลับของฟาร์ม และไม่ต้องการให้ role `developer` เห็นเป็น plaintext (เดิมเอกสารเขียนว่า developer เห็นข้อมูลปุ๋ย/ยาได้ปกติ — **requirement นี้ถูกแทนที่แล้ว**)
- เจ้าของอยากปิดข้อความกิจกรรมที่เป็น TEXT ยาวด้วย เพราะมักมีชื่อปุ๋ย/สูตรหลุดอยู่ในข้อความ
- Phase 1d ทำกลไกไว้แล้ว: Fernet, `app/services/secure_fields.py`, `encrypt_number`, `decrypt_number`, `present_number`, `present_aggregate`, response แยกตาม role พร้อม `is_masked` ให้ใช้ pattern เดียวกัน ห้ามสร้างกลไกเข้ารหัสใหม่คู่ขนาน
- ผู้ใช้ระบบจริงมีเจ้าของฟาร์มคนเดียว ข้อมูลน้อย จึงถอดรหัสแล้วกรองใน memory ได้ (เหมือนการค้นชื่อลูกค้า)

## Part A — Masking

### A1. สิ่งที่เข้ารหัส / ไม่เข้ารหัส

| ฟิลด์ | การจัดการ |
|---|---|
| `InputItem.item_name` | เข้ารหัส Fernet |
| `InputItem.quantity` | `encrypt_number` / `present_number` |
| `InputItem.unit` | plaintext |
| `InputApplication.note` | เข้ารหัส Fernet |
| `InputApplication.category`, `applied_date`, `cycle_id` | plaintext (ระบบรายงาน/คำแนะนำในอนาคตต้องอ้างหมวดหมู่ ไม่อ้างชื่อ) |
| `InputCatalog.item_name` | แทนด้วย `name_encrypted` + `name_hash` (ดู A2) |
| `InputCatalog.last_unit`, `last_category`, `last_used_at`, `use_count` | plaintext |
| `Task` ที่ `source = manual`: title และ description | เข้ารหัส (ดู A3) |
| `Task` ที่สร้างอัตโนมัติจาก lifecycle | plaintext (เป็นข้อความระบบ ไม่มีความลับ) |

ต้องตรวจ `models.py` ว่า Task มีฟิลด์ข้อความอื่นที่ owner พิมพ์เองอีกหรือไม่ ถ้ามีให้แจ้งก่อนตัดสินใจเอง

### A2. InputCatalog (จุดที่ซับซ้อนที่สุด)

- เพิ่ม `name_encrypted` (Fernet token) และ `name_hash` เป็น unique key แทน `item_name` เดิม
- `name_hash` = HMAC-SHA256 ของชื่อที่ normalize แล้ว (Unicode NFC, strip, casefold) ใช้ key ที่ derive จาก `ENCRYPTION_KEY` ด้วย context label แยก เช่น `b"input-catalog-name-hash:v1"` ห้ามใช้ `ENCRYPTION_KEY` ตรงๆ เป็น HMAC key และห้ามใช้ hash เปล่า (ไม่มี secret) เพราะเดาชื่อปุ๋ยยอดนิยมย้อนได้
- upsert จากการบันทึกปุ๋ย/ยา ใช้ `name_hash` หาแถวเดิม (คง semantics เดิม: case-insensitive match, อัปเดต `last_unit`, `last_category`, `last_used_at`, `use_count`)
- `GET /input-catalog/suggestions?q=&limit=`:
  - `owner`: ถอดรหัสทุกแถวใน memory, กรองด้วย casefold substring ของ `q`, เรียงตาม `use_count` แล้ว `last_used_at`, ตัดตาม `limit`, ส่งชื่อ plaintext
  - `developer`: คืน list ว่างและ `is_masked: true` (ห้ามส่ง ciphertext ของชื่อในรายการ suggestion)
- ยังคงห้าม seed InputCatalog ล่วงหน้า และห้าม hardcode รายชื่อปุ๋ย/ยา

### A3. Task (manual)

- เพิ่มคอลัมน์ `is_encrypted` (bool, default false) ไม่ย้ายคอลัมน์ ให้เก็บ Fernet token ลงใน title/description เดิมเมื่อ `is_encrypted = true`
- สร้าง/แก้ Task ที่ `source = manual` ผ่าน API → เข้ารหัสและตั้ง `is_encrypted = true` เสมอ
- `owner`: ได้ plaintext; `developer`: ได้ token พร้อม `is_masked: true`
- การค้นหา/กรองในหน้า Activities (owner): ถอดรหัสใน backend แล้วกรองใน memory
- `TaskWidget` บน Dashboard ต้องแสดงผลได้ทั้งสอง role (developer เห็นป้ายย่อ เช่น "ข้อมูลเข้ารหัส" ไม่ใช่ token ยาว)
- Task อัตโนมัติและ logic ของ `task_generator.py` ต้องไม่เปลี่ยน

### A4. Response และสิทธิ์

- ทุก endpoint ที่คืน InputApplication / InputItem / InputCatalog / Task ต้องกรองตาม role ที่ **response boundary ของ backend** (ไม่กรองแค่ใน frontend)
- `owner`: plaintext ทั้งหมด; `developer`: token + `is_masked: true` ทั้งชื่อ ปริมาณ และ note
- `developer` ยัง **เขียน** ปุ๋ย/ยาได้ (สะดวกตอนทดสอบ) แต่ตอบกลับเป็น ciphertext และเข้ารหัสฝั่ง server เสมอ
- ปริมาณเป็น `present_number` ถ้า Phase 2 ต้องรวมยอด ให้ถอดรหัสแล้ว aggregate ใน backend (ใช้ `present_aggregate`) — ตอนนี้ยังไม่ต้องทำรายงานรวมยอดปุ๋ย
- frontend: `PlotDetail` (ประวัติปุ๋ย/ยา, Edit Modal, Accordion) ต้องรองรับ `is_masked` สำหรับ developer โดยไม่พังและแสดงป้าย "ข้อมูลเข้ารหัส" `AutocompleteInput` เมื่อ developer ใช้ให้ไม่แสดง suggestion

### A5. กันรั่วทางอื่น

- ห้าม log request/response body ของ endpoint ปุ๋ย/ยา/Task; ตรวจ exception handler และ error message ไม่ให้ใส่ชื่อปุ๋ยหรือ note
- ห้ามนำชื่อปุ๋ยไปไว้ใน `Task` อัตโนมัติ, status log, ข้อความแจ้งเตือน หรือข้อความที่ developer เห็น
- ตรวจ export/seed/script ที่มีอยู่ว่าไม่เขียนข้อมูลปุ๋ยเป็น plaintext ลงไฟล์

### A6. Migration (ทำตามแบบ Phase 1d)

1. สำรอง SQLite ก่อน ชื่อ `erp-pre-phase1e-<timestamp>.db` ไปยังโฟลเดอร์สำรองที่จำกัดสิทธิ์ **นอก repo** (ไฟล์นี้มีข้อมูลปุ๋ยแบบ plaintext ห้าม commit ห้ามส่งให้ทีมพัฒนา ให้เตือนใน log ตอนรัน)
2. เข้ารหัสแถวเดิมของ `InputItem`, `InputApplication.note`, `InputCatalog` (สร้าง `name_hash`; ถ้าชื่อซ้ำกันหลัง normalize ให้รวมแถวโดย `use_count` บวกกัน และ `last_used_at` เอาค่าล่าสุด) และ Task manual เดิม
3. ตรวจ round-trip ทุกแถว (decrypt แล้วต้องตรงกับ plaintext เดิม) ก่อนตัดคอลัมน์ plaintext
4. ตัดคอลัมน์ plaintext (`item_name`, `quantity`, `note` เดิมของตารางที่เปลี่ยน), vacuum, ตรวจ `PRAGMA integrity_check`
5. รันซ้ำได้ (idempotent) และ fail ปลอดภัย: ถ้า round-trip ไม่ผ่านต้องไม่ตัดคอลัมน์และไม่ทิ้งฐานข้อมูลครึ่งๆ กลางๆ
6. ต้องไม่เริ่ม backend ถ้า `ENCRYPTION_KEY` ไม่ถูกต้อง (คง behavior จาก Phase 1d)

### A7. Tests (ต้องผ่านทั้งหมด)

- helper: normalize + `name_hash` คงที่สำหรับชื่อเดียวกัน, ต่างกันเมื่อชื่อต่างกัน, ไม่เปลี่ยนเมื่อรันซ้ำ
- InputApplication CRUD: owner ได้ plaintext, developer ได้ ciphertext + `is_masked`, DB ไม่มี plaintext (ตรวจจากไฟล์ DB/SQL ตรง)
- InputCatalog: upsert ชื่อซ้ำต่างตัวพิมพ์ → แถวเดียว; suggestions ของ owner กรอง/เรียง/limit ถูกต้อง; developer ได้ list ว่าง
- Task manual: เข้ารหัสใน DB, owner ค้นหาได้, developer ได้ token; Task อัตโนมัติยัง plaintext
- migration: ข้อมูลเดิมครบ, round-trip ผ่าน, รันซ้ำไม่เสียหาย, กรณี round-trip ล้มเหลวไม่ตัดคอลัมน์
- regression ของ Phase 1 / 1b / 1c / 1d ต้องผ่านเหมือนเดิม

## Part B — ช่องเก็บข้อมูลสำหรับเซนเซอร์และคำแนะนำ (ยังไม่ทำตรรกะคำแนะนำ)

เป้าหมาย: ให้ข้อมูลเริ่มสะสมตั้งแต่ตอนนี้ ข้อมูลเหล่านี้ **ไม่ใช่ความลับ ไม่ต้องเข้ารหัส**

### B1. ForecastSnapshot (ตารางใหม่ — ไม่แก้ `WeatherLog`)

`WeatherLog` เก็บค่า sync-yesterday (unique `log_date`) ซึ่งคือค่าย้อนหลัง ไม่ใช่ค่าพยากรณ์ จึงใช้เทียบ "พยากรณ์ถูกไหม" ไม่ได้

- ฟิลด์: `id`, `issued_at` (เวลาที่ดึง), `issued_date`, `target_date`, `lead_days`, `temp_min`, `temp_max`, `humidity`, `precip_probability`, `precip_mm`, `condition`, `source` (เช่น `open-meteo`), `created_at`
- unique (`issued_date`, `target_date`, `source`) เพื่อ upsert กันซ้ำเมื่อรันซ้ำในวันเดียว
- เพิ่ม APScheduler job รายวัน (หลัง sync-yesterday เช่น 08:05 `Asia/Bangkok`) เก็บพยากรณ์ 7 วันข้างหน้าด้วย service ตัวเดียวกับ `/weather/forecast` ห้ามทำซ้ำ logic การเรียก API
- ถ้าเรียก API ไม่สำเร็จ: log และข้ามรอบนั้น ห้ามทำให้ backend ล่ม

### B2. Catch-up ตอนสตาร์ท

- ตอน backend เริ่มทำงาน ตรวจ `WeatherLog` ย้อนหลัง 14 วันถึงเมื่อวาน วันไหนขาดให้ sync เติม (ใช้ upsert เดิม) ทำเป็น background และห้ามบล็อกการสตาร์ท
- เหตุผล: ระบบยังรันบนเครื่อง dev ที่อาจปิด/หลับตอน 08:00 (จนกว่าจะ deploy บน Pi)
- ForecastSnapshot ไม่ย้อนเติมได้ (พยากรณ์ในอดีตไม่มี) ไม่ต้องทำ catch-up ส่วนนี้

### B3. SensorReading + endpoint รับข้อมูล

- ตาราง `sensor_readings`: `id`, `device_id`, `sensor_type` (เช่น `rain_mm`, `temperature_c`, `humidity_pct`), `value` (float), `unit`, `recorded_at`, `received_at`
- unique (`device_id`, `sensor_type`, `recorded_at`) เพื่อให้ส่งซ้ำได้โดยไม่ซ้อนข้อมูล, index (`sensor_type`, `recorded_at`)
- `POST /sensors/readings` รับ list ได้หลายค่า (อุปกรณ์อาจส่งย้อนหลังที่บันทึกไว้ใน SD card) ยืนยันตัวตนด้วย header `X-Device-Token` เทียบกับค่า `DEVICE_TOKEN` จาก `.env` แบบ constant-time (`hmac.compare_digest`) **ไม่ใช้ JWT ของผู้ใช้** ถ้าไม่ได้ตั้ง `DEVICE_TOKEN` ให้ปิด endpoint นี้ (ตอบ 503) แทนที่จะเปิดโล่ง
- validate ช่วงค่าสมเหตุสมผลตาม `sensor_type` และ `recorded_at` ไม่เกินอนาคตมากเกินไป; ปฏิเสธทั้งชุดหรือรายแถวพร้อมรายงานชัดเจน
- `GET /sensors/readings?sensor_type=&from=&to=&limit=` ใช้ JWT (ทั้ง owner และ developer)
- เพิ่ม `DEVICE_TOKEN` ใน `.env.example`
- **ไม่ทำ** UI เซนเซอร์, ไม่ทำ logic เทียบพยากรณ์กับค่าจริง (ทำภายหลัง)

### B4. Recommendation (ตารางว่าง ไม่มี logic)

- ฟิลด์: `id`, `kind`, `title`, `message`, `reason`, `window_start`, `window_end`, `status` (`pending`/`acknowledged`/`done`/`dismissed`), `task_id` (FK Task, nullable — ใช้ Task reminder เป็นช่องทางส่งออกภายหลัง), `created_at`, `updated_at`
- แค่ model + migration ไม่ต้องมี router/UI
- **ตรวจ spec Phase 2 ข้อ 6** ที่กำหนดตาราง `Insight` + `GET /insights`: อย่าสร้างซ้ำซ้อน ให้แจ้งในผลงานว่าควรรวม `Insight` เข้ากับ `Recommendation` และแก้ roadmap ตามนั้น (ยังไม่ต้องแก้ spec Phase 2 เองถ้าไม่แน่ใจ)
- ข้อความในตารางนี้ในอนาคตต้องอ้างหมวดหมู่ (category) ไม่ใส่ชื่อปุ๋ยจริง เขียนเป็นหมายเหตุไว้ใน docstring ของ model

### B5. Tests

- ForecastSnapshot: upsert ซ้ำวันเดียวไม่เพิ่มแถว, API ล้มเหลวแล้ว job ไม่ crash (mock Open-Meteo)
- catch-up: เติมวันที่ขาด, ไม่แตะวันที่มีแล้ว, ล้มเหลวแล้วไม่บล็อกสตาร์ท
- sensors: token ผิด/ไม่มี → 401/403, ไม่ได้ตั้ง `DEVICE_TOKEN` → 503, ส่งชุดซ้ำไม่ซ้อน, ค่านอกช่วงถูกปฏิเสธ, `GET` ต้องใช้ JWT
- migration ของตารางใหม่รันซ้ำได้

## เอกสารที่ต้องอัปเดตในงานนี้

1. `PROJECT_CONTEXT.md` ส่วนความปลอดภัย: ข้อมูลที่ปิดบังจาก developer = ชื่อลูกค้า, ข้อมูลติดต่อ, ยอดรายได้ **+ ชื่อ/ปริมาณปุ๋ยและยา, note กิจกรรม, Task ที่ owner พิมพ์เอง**; ลบข้อความที่ว่า developer เห็นปุ๋ย/ยาได้ปกติ; ระบุขอบเขตการป้องกัน: กันการเห็นผ่านแอปเท่านั้น คนที่เข้า shell ของเครื่องและอ่าน `ENCRYPTION_KEY` ได้ยังถอดรหัสได้ และ production key ต้องเป็นของเจ้าของฟาร์มและสำรองแยกจากฐานข้อมูล
2. `PROJECT_STATUS.md`: เพิ่มแถว Revision History, ส่วน Database Models (ฟิลด์เข้ารหัส, ตารางใหม่), API (sensors), Phase 1e
3. `.env.example`: เพิ่ม `DEVICE_TOKEN` (และตัวแปร backup path ถ้ามี)

## สิ่งที่ไม่ทำในงานนี้

- ตรรกะคำแนะนำ/rule engine, UI เซนเซอร์, กราฟเทียบพยากรณ์กับค่าจริง
- ระบบสำรองข้อมูลอัตโนมัติและการ deploy บน Pi (Phase 3)
- เข้ารหัสทั้งดิสก์
- Phase 2 (สัญญา/ออเดอร์/ต้นทุน)

## Acceptance Criteria

- owner เห็นข้อมูลปุ๋ย/ยา/ปริมาณ/note/Task manual เป็น plaintext ทุกหน้า
- developer เห็น ciphertext + `is_masked` ในทุก endpoint ที่เกี่ยวข้อง และ UI ไม่พัง
- ไม่พบ plaintext ของข้อมูลที่ระบุใน DB, log และ error message
- migration ข้อมูลเดิมสำเร็จ ตรวจ round-trip, `integrity_check` ผ่าน และมีไฟล์สำรองนอก repo
- ForecastSnapshot มีข้อมูลเข้ามาทุกวัน, catch-up ทำงาน, `POST /sensors/readings` ใช้งานได้ด้วย `X-Device-Token`
- backend tests ทั้งหมดผ่าน (รวม Phase 1–1d เดิม) และ `npm run build` ผ่าน
- เอกสารทั้งสามไฟล์อัปเดตครบ และรายงานสรุปสิ่งที่เปลี่ยน พร้อมข้อสังเกตเรื่อง `Insight` vs `Recommendation`
