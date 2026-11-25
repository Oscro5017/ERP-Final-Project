# ERP Project Status

## Phase 2 backend

Slices 2.1–2.5 plus stock reads and dashboard are implemented on `backend/products-stock`. Regression after 2.5: 221 passed, 73 warnings. The Phase 2 end-to-end workflow test passes. API handoff: `docs/API_PHASE2.md`; generated schema: `docs/openapi.phase2.json`; progress: `docs/phases/phase2/PROGRESS.md`. No commit or push has been made.

วันที่ตรวจสอบ: 2026-11-06

## ภาพรวม

ระบบหลักทำงานด้วย FastAPI + SQLAlchemy backend และ React/Vite frontend โดย `ERPOganicFarm` เป็นโปรเจกต์หลัก ส่วน `code_prototype` ใช้เก็บต้นแบบ UI สำหรับเปรียบเทียบ

ปัจจุบัน Phase 1b–1e มี implementation ตามขอบเขตแล้ว: Task/Weather, Chart.js/data hooks, encrypted customer/input/task data, forecast snapshots และ sensor endpoints. Backend hygiene H1–H6 ได้ตรวจและปรับปรุงต่อเนื่องใน branch `backend/safe-decrypt-logging` พร้อมงาน follow-up S1–S4: safe per-row decryption, redacted logging, rotating app logs, read-only decrypt checker, และ config password iteration ที่สามารถยกระดับ hash ได้ตามค่าใหม่. Full backend suite ล่าสุดวันที่ 2026-11-06 ผ่าน 77 tests และมี 73 warnings; ยังไม่ได้เปิดหรือแก้ `erp.db` จริง, ยังไม่ได้รัน foreign-key audit กับสำเนาฐานข้อมูลจริงหรือสั่ง historical re-sync; ให้ทำ audit ก่อน deploy การบังคับ foreign keys. Phase 2 ยังไม่เริ่ม

> **วันที่ปรับปรุงล่าสุด**: 2026-11-06
> **รายละเอียด**: เพิ่ม safe decrypt/secure logging, จัดการ rotating log `logs/app.log`, read-only decrypt audit script, config `PASSWORD_HASH_ITERATIONS`, และรวม patch validation อย่างต่อเนื่อง. Full backend suite รันจริงวันที่ 2026-11-06: 77 passed, 73 warnings; frontend build ผ่าน. ไม่ได้เปิดหรือแก้ `erp.db` จริง. งาน backend hygiene H1–H6 และ follow-up S1–S4 ยังคงมีผลตามบันทึกรอบก่อน.

## ประวัติการปรับปรุงระบบ (Revision History)

| วันที่ (Date) | รายละเอียดการปรับปรุง (Changes) | AI Model | โปรแกรม / เครื่องมือ (Platform) |
|---|---|---|---|
| 2026-11-06 | เพิ่ม safe decrypt/logging สคริปต์, rotating log, read-only decrypt checker, `PASSWORD_HASH_ITERATIONS` และตรวจสอบ callback/response ที่รั่ว token; full backend suite 77 passed, 73 warnings; frontend build ผ่าน | GitHub Copilot | VS Code |
| 2026-11-06 | แก้ `/weather` SPA refresh fallback และเปลี่ยน weather history ให้แสดงทุกบันทึกเป็นค่าเริ่มต้น; backend tests 66 passed, 73 warnings; frontend build ผ่าน | GitHub Copilot | VS Code |
| 2026-11-05 | ตรวจ/ปิดงาน backend hygiene H1–H6 และ follow-up; full backend suite รันจริง 65 passed, 73 warnings; ไม่ได้เปิด/แก้ `erp.db` จริง, ไม่ได้รัน foreign-key audit กับสำเนาฐานข้อมูลจริงหรือ historical re-sync | GitHub Copilot | VS Code |
| 2026-11-03 | ตรวจพบ scheduled weather sync บน Pi ได้ HTTP 503 จาก Open-Meteo; sync วันที่ 2026-11-02 สำเร็จภายหลังและมีประวัติ 17 วัน; เพิ่ม retry สูงสุด 3 attempts และ daily 14-day catch-up เวลา 08:30 ใน workspace; tests weather/scheduler/catch-up 23 passed; รอ deploy ไป Pi | Copilot | VS Code |
| 2026-11-02 | Backend hygiene H1–H6: SQLite PRAGMAs/FK audit utility, scheduler recovery, weather validation/cache, production hardening, backup config และ deployment docs; full backend tests 56 passed, 73 warnings; ไม่ได้ตรวจ `erp.db` จริงหรือรัน historical re-sync | Codex | Codex |
| 2026-10-30 | Phase 1e: เข้ารหัส input/catalog/manual task, เพิ่ม forecast snapshots, weather catch-up, sensor API และ Recommendation model; สำรอง/มigrate DB จริง, tests 26/26 และ frontend build ผ่าน | - | GitHub Copilot |
| 2026-10-20 | Phase 1d: เข้ารหัส contact และตัด plaintext column, backup/migration ตรวจ round-trip, customer ciphertext แยก role, secure number helpers, tests ผ่าน | - | GitHub Copilot |
| 2026-10-20 | Phase 1c: ย้ายกราฟ Recharts ไป Chart.js, เพิ่ม yield/status history/timestamps/soft delete, migrate SQLite เดิมและ backfill; tests 10/10, build ผ่าน | - | GitHub Copilot |
| 2026-10-20 | เชื่อม TaskWidget กับ Dashboard, เปลี่ยน Activities จาก mock เป็น Task API CRUD, ใช้วันอังคารถัดไปเป็นค่าเริ่มต้น, แก้ Tailwind v4 config; pytest 7/7 และ frontend build ผ่าน | - | GitHub Copilot |
| 2026-10-20 | ตั้งพิกัดจุดกึ่งกลางฟาร์ม 18.8072866, 99.0930437 และ sync 08:00 Asia/Bangkok; ซ่อม import ของ Task tests, backend tests 7/7 ผ่าน; สำรอง `erp.db` เป็น `erp-pre-phase1c-20261020.db` และ SQLite integrity check ผ่าน | - | GitHub Copilot |
| 2026-09-30 | ตรวจเทียบสถานะจริงกับ PROJECT_CONTEXT.md และ specs; บันทึกงานค้าง Phase 1 ต่อและช่องว่างด้านการเข้ารหัสข้อมูลติดต่อ | - | Codex |
| 2026-09-21 | ปรับปรุง Roadmap และลำดับงานที่แนะนำใน PROJECT_STATUS.md ให้ตรงตาม PROJECT_CONTEXT.md (เน้น Task reminder และ WeatherLog ก่อนตาม requirement จริงของเจ้าของฟาร์ม) | Gemini 3.8 Flash | Antigravity |
| 2026-09-21 | พัฒนา Phase 1: InputApplication (บันทึกปุ๋ย/ยา) สมบูรณ์ 100% (Backend endpoints, AutocompleteInput component, Edit Modal, Delete Handler, Accordion View, Pytest 3/3 ผ่าน, Build ผ่าน) | Gemini 3.8 Flash | Antigravity |
| 2026-09-20 | คืนสภาพ backend ให้เป็น FastAPI/Python ตามเอกสารและสถาปัตยกรรมที่ระบุไว้จริงของโปรเจกต์ | - | VScode |
| 2026-09-08 | ตรวจสอบระบบและเริ่มต้นจัดทำเอกสารสถานะโครงการ Phase 0 | - | VScode |

## วัตถุประสงค์ของโปรเจกต์

ระบบนี้เป็นต้นแบบ Organic Farm ERP สำหรับจัดการฟาร์มไฮโดรโปนิกส์ โดยมีเป้าหมายให้ผู้ใช้ติดตามรอบการปลูก แปลงเพาะปลูก ลูกค้า ผลผลิต สต็อก การขาย ต้นทุน และรายงานจากระบบเดียว

`ERPOganicFarm` เป็นโปรเจกต์หลักที่รวม backend และ frontend เข้าด้วยกัน ส่วน `code_prototype` เป็นต้นฉบับ UI ที่เก็บแยกไว้เพื่อเปรียบเทียบหน้าตาและ workflow

## สถาปัตยกรรมระบบ

```text
Browser / React dashboard
	|
	| HTTP JSON + JWT Bearer token
	v
FastAPI application
	|
	| SQLAlchemy ORM
	v
SQLite database (erp.db)
```

### Backend

- Python, FastAPI และ Uvicorn
- SQLAlchemy 2 สำหรับ ORM และการเชื่อมฐานข้อมูล
- Pydantic Settings สำหรับอ่านค่าจาก `.env`
- JWT สำหรับ authentication
- Fernet สำหรับเข้ารหัสชื่อลูกค้า/ข้อมูลติดต่อ และเตรียมข้อมูลตัวเลขลับสำหรับ Phase 2
- SQLite เป็นค่าเริ่มต้น สามารถเปลี่ยน database URL ได้
- Swagger/OpenAPI อยู่ที่ `/docs`

### Frontend

- React 18
- Vite
- React Router
- Tailwind CSS
- Lucide React สำหรับ icon
- Chart.js ผ่าน `react-chartjs-2` และ shared chart wrappers
- Vite build output อยู่ที่ `frontend/` เพื่อให้ FastAPI serve ได้โดยตรง

## โครงสร้างโฟลเดอร์

```text
ERPOganicFarm/
├── app/
│   ├── main.py              # สร้าง FastAPI, register router และ serve React
│   ├── config.py            # settings จาก environment
│   ├── database.py          # engine, session และ Base
│   ├── encryption.py        # compatibility helpers เดิมสำหรับ Fernet
│   ├── models.py             # SQLAlchemy models
│   ├── schemas.py            # request/response schemas
│   ├── security.py           # password hash, JWT และ current user/role
│   ├── migrations.py         # migration สำหรับ CropCycle เดิม
│   ├── seed.py               # ข้อมูลเริ่มต้น
│   ├── services/
│   │   ├── secure_fields.py # เข้ารหัสและนำเสนอข้อมูลลับตาม role
│   │   ├── input_catalog.py  # upsert และ suggestion catalog
│   │   ├── task_generator.py # สร้าง/อัปเดตงานจากสถานะ CropCycle
│   │   └── weather.py        # พยากรณ์และบันทึกสภาพอากาศ
│   └── routers/
│       ├── auth.py            # login
│       ├── customers.py       # customer API
│       ├── crop_cycles.py     # crop cycle API
│       ├── input_applications.py # input applications & suggestions API
│       ├── tasks.py          # Task Reminder API
│       ├── weather.py        # Weather forecast/history/sync API
│       ├── sensors.py        # Sensor ingestion/read API
│       └── reference.py       # tables, batches, crop types
├── src/
│   ├── App.jsx                # authentication gate และ routes
│   ├── lib/api.js             # fetch helper และ login
│   ├── layouts/               # Dashboard layout
│   ├── components/            # shared UI components (รวม AutocompleteInput, Modal)
│   ├── pages/                 # แต่ละหน้าของระบบ (PlotDetail บันทึกปุ๋ย/ยา)
│   └── data/mockData.js        # ข้อมูลจำลองของหลายโมดูล
├── tests/
│   ├── test_input_applications.py # tests สำหรับ Phase 1
│   ├── test_tasks.py              # tests สำหรับ Task Reminder
│   ├── test_weather.py            # tests สำหรับ WeatherLog
│   ├── test_phase1e_migrations.py # tests migration/encryption Phase 1e
│   └── test_phase1e_data_hooks.py # tests weather/sensor hooks Phase 1e
├── frontend/                  # production build ที่ FastAPI serve
├── .env                       # ค่าลับและ database configuration
├── .env.example               # ตัวอย่าง environment variables
├── requirements.txt            # Python dependencies
├── package.json                # Node dependencies และ scripts
├── vite.config.js              # Vite build/proxy configuration
├── tailwind.config.js          # Tailwind theme
├── erp.db                      # SQLite database ปัจจุบัน
└── PROJECT_STATUS.md           # เอกสารบริบทและงานค้าง
```

## Database Models ปัจจุบัน

### User

- `id`
- `username`
- `password_hash`
- `role`: `owner` หรือ `developer`

### Table

แทนโต๊ะหรือพื้นที่ปลูก มี `table_number` ที่ไม่ซ้ำกัน

### Batch

แทนรอบการปลูก มี batch number, วันที่เริ่มต้น และ week offset

### CropType

ชนิดพืช มีชื่อพืช จำนวนวัน nursery และจำนวนวัน growth

### CropCycle

เชื่อม `Table`, `Batch` และ `CropType` เข้าด้วยกัน มีวันที่ nursery, transplant, harvest และสถานะรอบการปลูก

`CropCycle` มี `cycle_code` รูปแบบ `YYMMDD` ที่สร้างจาก `nursery_start`

มี `harvest_quantity_kg` สำหรับน้ำหนักที่เก็บได้จริง, `created_at`, `updated_at`, `deleted_at` และประวัติสถานะใน `CropCycleStatusLog`

สถานะที่ backend รองรับ:

- `nursery`
- `bushed`
- `ready_to_harvest`
- `harvested`
- `empty`

การให้ปุ๋ยและการใส่ยาไม่ใช่สถานะของ CropCycle แต่แยกเป็นโมดูล InputApplication ใน Phase 1

### Customer

- `id`
- `name_encrypted`: ชื่อลูกค้าที่เก็บเป็น encrypted bytes
- `contact_encrypted`: Fernet token ของข้อมูลติดต่อ; ไม่มี plaintext contact column ในฐานข้อมูล
- มี `created_at`, `updated_at` และ `deleted_at`; การลบผ่าน API เป็น soft delete

ข้อกำหนดใน `PROJECT_CONTEXT.md` คือชื่อลูกค้า ข้อมูลติดต่อ และยอดรายได้ต้องเข้ารหัสในฐานข้อมูล ปัจจุบันชื่อและ contact ถูกเข้ารหัสแล้ว; ระบบรายได้ยังไม่เริ่มตามขอบเขต Phase 2

### InputCatalog (Phase 1)

แคชประวัติชื่อปุ๋ย/ยาสำหรับระบบ Autocomplete (ไม่มีการ seed ล่วงหน้า เกิดจากการใช้งานจริงเท่านั้น):
- `id`
- `name_encrypted`: ชื่อวัตถุดิบ/ปุ๋ย/ยาที่เข้ารหัสด้วย Fernet
- `name_hash`: HMAC-SHA256 ที่ derive จาก `ENCRYPTION_KEY` หลัง normalize Unicode NFC/strip/casefold; unique ใช้ค้นและ upsert โดยไม่เก็บ plaintext
- `last_unit`: หน่วยที่ใช้ล่าสุด
- `last_category`: ประเภทที่ใช้ล่าสุด
- `last_used_at`: วันเวลาที่ใช้ล่าสุด
- `use_count`: จำนวนครั้งที่ใช้

### InputApplication & InputItem (Phase 1)

บันทึกการให้ปุ๋ย/ยาของแต่ละรอบการปลูก:
- `InputApplication`: `id`, `cycle_id` (FK CropCycle), `applied_date`, `category`, `note_encrypted`
- `InputItem`: `id`, `application_id` (FK InputApplication), `item_name_encrypted`, `quantity_encrypted`, `unit`
- ทั้งสองมี `created_at`/`updated_at`; InputApplication มี `deleted_at` และลบแบบ soft delete
- owner ได้ plaintext; developer ได้ token พร้อม `is_masked`; `unit`, `category` และวันที่เป็น plaintext

### Task, Weather และ sensor data (Phase 1b/1e — implementation พร้อมใช้งาน; รอยืนยัน scheduled run)

- `Task`: งาน manual/auto ผูกกับ CropCycle ได้ พร้อม due date, status, source และ created_at; manual title เก็บเป็น Fernet token และ `is_encrypted=true`, auto title เป็น plaintext
- `WeatherLog`: สภาพอากาศรายวัน ประกอบด้วยอุณหภูมิต่ำสุด/สูงสุด ความชื้น ฝน สภาพอากาศ และเวลาที่ดึงข้อมูล
- `ForecastSnapshot`: พยากรณ์รายวันตาม issued/target date, lead time, อุณหภูมิ, ความชื้น, โอกาสฝนและปริมาณฝน; unique ต่อวันออกพยากรณ์/วันเป้าหมาย/source
- `SensorReading`: ข้อมูลจาก sensor มี unique ต่อ device/type/recorded time และ index ตาม type/time
- `Recommendation`: ช่องเก็บคำแนะนำว่าง ยังไม่มี rule engine, API หรือ UI; ก่อน Phase 2 ให้รวมแนวคิดกับ `Insight` เดิมเป็น resource เดียว
- Task มี `created_at`, `updated_at`, `deleted_at`; WeatherLog มี `created_at`, `updated_at` ควบคู่กับ `fetched_at`

## API ปัจจุบัน

### Authentication

```text
POST /auth/login
```

รับ username/password และคืน JWT กับ role

### Reference data

```text
GET /tables
GET /batches
GET /crop-types
```

ทุก endpoint ต้องใช้ JWT

### Crop cycles

```text
GET   /crop-cycles
POST  /crop-cycles
PATCH /crop-cycles/{cycle_id}
DELETE /crop-cycles/{cycle_id}
GET   /crop-cycles/{cycle_id}/status-log
```

ข้อมูล crop cycle จะคืน relation ของ table, batch และ crop type มาด้วย

### Input Applications (Phase 1)

```text
GET    /crop-cycles/{cycle_id}/input-applications
POST   /crop-cycles/{cycle_id}/input-applications
PATCH  /input-applications/{id}
DELETE /input-applications/{id}
GET    /input-catalog/suggestions?q={query}&limit=10
```

- รองรับการบันทึกสูตรผสมหลายไอเท็มพร้อมกัน (nested items)
- อัปเดต `InputCatalog` อัตโนมัติทุกครั้งที่มีการบันทึกหรือแก้ไข
- owner เห็นข้อมูลจริง; developer ยังเขียนได้แต่ response เป็น ciphertext พร้อม `is_masked`; autocomplete ของ developer คืน `items: []`, `is_masked: true`

### Task Reminder และ Weather (Phase 1b — implementation เสร็จ; รอยืนยัน scheduled run)

```text
GET/POST       /tasks
PATCH/DELETE   /tasks/{id}
GET            /weather/forecast
GET            /weather/history
POST           /weather/sync-yesterday
GET/POST       /sensors/readings
```

- CropCycle เรียก service เพื่อสร้าง/อัปเดต task อัตโนมัติตาม lifecycle
- APScheduler ตั้งงาน sync สภาพอากาศเมื่อวานทุกวันเวลา 08:00 `Asia/Bangkok`
- Weather sync ใช้ upsert และ `WeatherLog.log_date` มี unique constraint
- `TaskWidget` แสดงงาน pending ที่ครบกำหนดภายใน 7 วันบน Dashboard และกดทำเสร็จได้
- หน้า `/activities` ใช้ Task API จริง พร้อมค้นหา/กรอง/เพิ่ม/แก้ไข/ลบ/เปลี่ยนสถานะ
- Vite dev proxy รองรับ `/tasks`, `/weather`, `/sensors`, `/input-applications` และ `/input-catalog`
- พิกัด Open-Meteo ตั้งเป็นจุดกึ่งกลางฟาร์มที่เจ้าของยืนยันแล้ว (18.8072866, 99.0930437)
- ตั้งเวลา daily weather sync เป็น 08:00 ตามเวลา `Asia/Bangkok`; log บน Pi ยืนยันเหตุการณ์ Open-Meteo 503 วันที่ 2026-11-03 และผู้ใช้ซิงก์วันที่ 2026-11-02 สำเร็จภายหลัง
- โค้ด workspace เพิ่ม retry สูงสุด 3 attempts (backoff 1 และ 2 วินาที) และ daily catch-up เวลา 08:30 เติมข้อมูลที่ขาดย้อนหลัง 14 วัน; ต้อง deploy/restart บน Pi ก่อนจึงมีผลใน production
- ForecastSnapshot ใช้ service `get_live_forecast` เดียวกับ `/weather/forecast` และบันทึกทุกวันเวลา 08:05; job failure ถูก log และไม่ทำให้ backend ล่ม
- ตอน startup มี background catch-up เติม WeatherLog ที่ขาดใน 14 วันก่อนหน้าโดยไม่บล็อกการเริ่ม API; เพิ่ม daily catch-up เวลา 08:30 เพื่อ retry วันที่ยังขาดโดยไม่ต้อง restart ระบบ
- `POST /sensors/readings` ใช้ `X-Device-Token` แบบ constant-time; ถ้าไม่ได้ตั้ง `DEVICE_TOKEN` จะตอบ 503; `GET` ต้องใช้ JWT

### Customers

```text
GET  /customers?q={owner_name_query}
POST /customers
```

`DELETE /customers/{customer_id}` ทำ soft delete; การแสดงผลตาม role:

- `owner`: เห็นชื่อจริงและข้อมูลติดต่อ
- `developer`: เห็น Fernet ciphertext ของชื่อและ contact พร้อม `is_masked: true`; UI แสดง token แบบย่อและคัดลอกค่าเต็มได้

ชื่อและ contact เก็บเป็น Fernet token ในฐานข้อมูลโดยไม่มี plaintext contact column; owner ค้นชื่อโดย backend ถอดรหัสและกรองในหน่วยความจำ ส่วน developer ค้นชื่อไม่ได้

## Authentication และการทำงานของ Frontend

1. ผู้ใช้กรอก username/password ที่หน้า Login
2. React เรียก `POST /auth/login`
3. JWT ถูกเก็บใน `localStorage` key `organic_farm_token`
4. `src/lib/api.js` แนบ token เป็น `Authorization: Bearer <token>` ทุก request
5. App แสดง Dashboard เมื่อพบ token
6. Logout ลบ token และกลับหน้า Login

หาก API ตอบ 401 ระหว่างใช้งาน `src/lib/api.js` จะลบ token และ redirect ไป Login พร้อมข้อความ `เซสชันหมดอายุ กรุณาเข้าสู่ระบบใหม่`

## Frontend Routes

```text
/                 Dashboard
/plots            Farm Plots
/plots/:id        Plot Detail
/activities       Activities
/harvest          Harvest
/inventory        Inventory
/sales            Sales
/costs            Costs
/reports          Reports
/users            Users
/settings         Settings
```

หน้าเหล่านี้ใช้ layout ร่วมกันจาก `DashboardLayout`, `Sidebar` และ `Navbar`

## Seed Data และบัญชีทดสอบ

เมื่อเริ่มระบบครั้งแรก `seed.py` จะสร้าง:

- ผู้ใช้ `owner / owner123`
- ผู้ใช้ `developer / developer123`
- tables 1-49
- batches 1-8
- crop types: Green Oak, Red Oak และ Frilly
- crop cycles เริ่มต้น 8 รายการ

การ seed ปัจจุบันหยุดทันทีถ้าพบ user `owner` อยู่แล้ว ดังนั้นการแก้ seed จะไม่เติมข้อมูลให้ database เดิมโดยอัตโนมัติ

## Environment Variables

ค่าหลักอยู่ใน `.env`:

```env
DATABASE_URL=sqlite:///./erp.db
JWT_SECRET=change-this-in-production
JWT_EXPIRE_MINUTES=480
ENCRYPTION_KEY=<fernet-key>
CORS_ORIGINS=http://localhost:8000,http://127.0.0.1:8000
```

ห้าม commit `.env` หรือเปิดเผย `JWT_SECRET` และ `ENCRYPTION_KEY` ใน production

## วิธีติดตั้งและเปิดระบบ

### Backend และ production frontend

```powershell
cd D:\ProjectCode\ERPOganicFarm
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
npm install
npm run build
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

เปิดใช้งานที่ `http://127.0.0.1:8000` และดู API ที่ `http://127.0.0.1:8000/docs`

### Frontend development server

```powershell
npm run dev
```

Vite ใช้ port 3000 และ proxy request ของ API ไปที่ FastAPI port 8000 การแก้ frontend ด้วย dev server ต้องเปิด FastAPI แยกอีก terminal หนึ่ง

## ความสัมพันธ์กับ code_prototype

`code_prototype` เป็น React UI ต้นฉบับที่มีหน้าจอและ mock workflow ครบกว่า โดยมี Dashboard, plots, activities, harvest, inventory, sales, costs, reports, users และ settings

โค้ด React ถูกนำมาไว้ใน `ERPOganicFarm/src` แล้ว ส่วน `code_prototype` ไม่ควรแก้ไข เพื่อใช้เป็น baseline เปรียบเทียบหน้าตาและพฤติกรรม

สิ่งที่มาจาก prototype แต่ยังไม่ได้ทำเป็นระบบจริงคือข้อมูล dashboard, inventory, sales, costs, reports, activities, harvest และ users

## สิ่งที่ทำงานแล้ว

- Login ด้วย JWT ผ่าน `POST /auth/login`
- Logout และล้าง token จาก browser
- Sidebar navigation และยุบ/ขยาย sidebar
- Route หลักของระบบ
- Customer panel เรียก `GET /customers` และ `POST /customers`
- Owner เห็นชื่อลูกค้าและข้อมูลติดต่อจริง
- Developer เห็น ciphertext ของชื่อและ contact พร้อม `is_masked: true`
- Backend มี API สำหรับ tables, batches, crop types และ crop cycles
- CropCycle ใช้สถานะใหม่ 5 ค่าและมี `cycle_code` อัตโนมัติ
- มี startup migration สำหรับเพิ่ม `cycle_code` และ map สถานะ legacy โดยไม่ลบข้อมูล พร้อม log รายการที่ถูก map
- หน้า Farm Plots เรียก reference APIs และ `/crop-cycles` จริง มี search/filter และ CRUD ที่คงอยู่หลัง refresh
- ปุ่มดูรายละเอียดจาก Farm Plots เปิดข้อมูลตาม CropCycle ID จริง
- Plot Detail ใช้ route parameter และแสดงหน้าไม่พบข้อมูลเมื่อ ID ไม่ถูกต้อง
- Global 401 handler ล้าง token และ redirect ไป Login เมื่อ session หมดอายุ
- Modal และ Toast ทำงานได้
- **Phase 1: โมดูล InputApplication (บันทึกการให้ปุ๋ย/ยา) สมบูรณ์ 100%**:
  - บันทึกการให้ปุ๋ย/ยาผูกกับแต่ละรอบการปลูก (`POST /crop-cycles/{id}/input-applications`) รองรับรายการผสมหลายไอเท็ม
  - ระบบ Autocomplete แนะนำชื่อวัตถุดิบและหน่วยอัตโนมัติจากประวัติการกรอก (`GET /input-catalog/suggestions`) ด้วย debounce 300ms
  - Component กลาง `src/components/AutocompleteInput.jsx` นำกลับมาใช้ซ้ำได้
  - ปรับปรุง UI ประวัติการให้ปุ๋ย/ยาแบบ Accordion/Expandable ดูรายการส่วนผสมได้อย่างเป็นระเบียบ
  - รองรับการแก้ไขรายการ (Edit Modal) ยิง `PATCH /input-applications/{id}` พร้อม auto-sync UI
  - รองรับการลบรายการ (Delete Handler) ยิง `DELETE /input-applications/{id}` พร้อมการยืนยันก่อนลบ
  - Developer role สามารถเข้าถึงและบันทึกข้อมูลได้ตามข้อกำหนด
  - เพิ่ม Unit/Integration tests ครอบคลุม CRUD และสิทธิ์การเข้าถึง (`tests/test_input_applications.py`)
- **Phase 1 ต่อ: Task Reminder พร้อมใช้งานใน frontend แล้ว**:
  - มี model และ API สำหรับ list/filter, create, update/mark done และ delete task
  - สร้าง/อัปเดต task อัตโนมัติเมื่อสร้างหรือแก้ CropCycle ตามสถานะและช่วงวันของ CropType
  - `TaskWidget` แสดงงานใกล้กำหนดบน Dashboard และรองรับ mark done/เพิ่มงาน manual
  - หน้า Activities แสดงรายการจาก Task API จริง พร้อมค้นหา/กรอง/CRUD
  - ฟอร์ม Farm Plots ตั้งค่าเริ่มต้นวันอังคารถัดไปและยังแก้วันที่ได้
- **Phase 1b: Weather backend และ widget พร้อมใช้งาน**:
  - ดึง forecast จาก Open-Meteo พร้อมอุณหภูมิ ฝน ความชื้น และ condition
  - เก็บ WeatherLog ด้วย endpoint sync และมี APScheduler ตั้งเวลารายวัน พร้อม upsert กันข้อมูลซ้ำ
  - `WeatherWidget` แสดงข้อมูลพยากรณ์ละเอียด
  - พิกัดฟาร์มที่เจ้าของยืนยันแล้วคือ 18.8072866, 99.0930437; scheduled job ยังรอยืนยันกับ Open-Meteo บน environment จริง

## Roadmap และงานที่ต้องทำต่อ (อ้างอิงจาก PROJECT_CONTEXT.md)

> **คำเตือนสำคัญ**: ห้ามนำเอาโครง UI จาก `code_prototype` (เช่น Inventory, Sales, Costs) มากำหนดลำดับงานก่อนความต้องการจริงของเจ้าของฟาร์ม ให้ยึดลำดับตาม Roadmap ด้านล่างนี้เสมอ

### Phase 1 ต่อ — งานที่ต้องทำก่อนเริ่ม Phase 2

Implementation ของ Task Reminder และ WeatherLog ครบตามขอบเขตโค้ดแล้ว; ก่อนปิด Phase 1b อย่างสมบูรณ์ยังต้องตรวจยืนยันภายนอกตาม acceptance criteria ใน `Project-Phase/erp-farm-phase1b-task-weather-prompt.md`:

1. **ตรวจ scheduled weather sync ใน environment จริง**: ตั้งเวลาเป็น 08:00 ตามเวลาไทยและบันทึกพิกัดที่เจ้าของยืนยันแล้ว; ยังต้องยืนยันว่า APScheduler ทำงานตามเวลาที่ตั้งและบันทึกข้อมูลจาก Open-Meteo ได้
2. **ตรวจ acceptance ใน browser**: ทดสอบ Dashboard task widget, Activities CRUD, วันอังคารถัดไป และ weather widget หลังรันระบบจริง

การตรวจล่าสุด: backend tests ผ่าน 7 tests, `npm run build` ผ่าน และ next-Tuesday helper ผ่าน 3 กรณีวันที่

ไฟล์สำรองก่อน migration (`erp-pre-phase1c-20261020.db` และ `erp-pre-phase1d-20261020-200045-507381.db`) มี contact แบบ plaintext; เก็บไว้เฉพาะเจ้าของฟาร์มในโฟลเดอร์ backup ที่จำกัดสิทธิ์นอก repo ห้ามส่งให้ทีมพัฒนา ไฟล์ใน workspace ถูกย้ายออกแล้ว

### Phase 1c — implementation เสร็จ

- กราฟใน `PlotChart` และ `RevenueChart` ใช้ wrappers ที่ `src/components/charts/`; ไม่มี import/package ของ Recharts เหลือ
- เพิ่ม harvest quantity ใน schema, API และหน้า Farm Plots/Plot Detail
- เพิ่ม status-log service/endpoint/timeline และ initial logs สำหรับ seed cycles
- เพิ่ม timestamps/soft delete, active query helper และ startup migration/backfill ที่รันซ้ำได้
- ย้ายข้อมูลใน `erp.db`; ตรวจจำนวนแถวเดิมและ status logs ครบ, timestamp backfill ไม่มี null
- Backup ก่อน migration: `erp-pre-phase1c-20261020.db` (SQLite integrity `ok`)
- Verification: backend tests 10/10, `npm run build` ผ่าน, Dashboard มี Chart.js canvas 2 ชุด, ไม่พบ Recharts ใน source/package

### Phase 1d — Security Alignment เสร็จ

- `Customer` เก็บชื่อและ contact เป็น Fernet token; migration สำรอง SQLite ก่อน, ตรวจ round-trip ทุกแถว, ตัดคอลัมน์ plaintext และ vacuum ฐานข้อมูล
- Owner ได้ plaintext และค้นชื่อผ่านการถอดรหัส/กรองใน backend; developer ได้ ciphertext โดยไม่ decrypt พร้อม `is_masked`
- เพิ่ม helper `encrypt_number`, `decrypt_number`, `present_number` และ `present_aggregate` สำหรับตัวเลขลับ; ยังไม่มีตารางหรือข้อมูลรายได้จริง
- Phase 2 ต้องรวม/จัดกลุ่มตัวเลขหลัง decrypt ใน backend; developer ต้องได้ aggregate token ใหม่พร้อม `is_masked: true` และกราฟแสดงสถานะข้อมูลเข้ารหัส
- `ENCRYPTION_KEY` ต้องถูกตั้งและเป็น Fernet key ที่ถูกต้องก่อนเริ่ม backend; production key เป็นของเจ้าของฟาร์มและต้องสำรองแยกจากฐานข้อมูล
- Tests ครอบคลุม helpers, backup/migration/rerun, round-trip, owner/developer response และการค้นหา

### Phase 1e — Input masking และ data hooks เสร็จ

- `InputItem.item_name`, `quantity`, `InputApplication.note`, `InputCatalog` name และ manual Task title เข้ารหัสด้วย Fernet; developer ได้ token พร้อม `is_masked`, owner ได้ plaintext
- Catalog lookup ใช้ HMAC-SHA256 ที่ derive ด้วย HKDF จาก Fernet key; owner ค้น/เรียง suggestions ใน backend, developer ได้ list ว่าง
- `Task` ปัจจุบันไม่มี description field เพิ่มเติม; Task auto และ lifecycle generator ยังคง plaintext/logic เดิม
- Migration จริงสร้าง backup ก่อนที่ `D:\ProjectCode\ERPOganicFarm-private-backups\phase1e` พร้อม ACL เฉพาะบัญชีเจ้าของ, ตรวจ round-trip, ลบคอลัมน์ plaintext, vacuum และตรวจ integrity `ok`
- Live DB verification เทียบข้อมูล owner กับ backup, scan ไม่พบข้อความ private เดิมใน `erp.db`; migration rerun ไม่แปลงซ้ำ
- เพิ่ม `ForecastSnapshot`, job 08:05 `Asia/Bangkok`, 14-day WeatherLog catch-up แบบ background, `SensorReading` และ `POST/GET /sensors/readings`; live Open-Meteo smoke capture บันทึก 7 snapshots แล้ว
- 422 validation response ตัดค่า `input`/context ออกเพื่อไม่ echo ชื่อวัตถุดิบหรือ note ที่ส่งมาใน request ที่ไม่ผ่าน validation
- เพิ่ม model-only `Recommendation`; ยังไม่มี rule engine/API/UI; ต้อง reconcile กับ `Insight` ใน Phase 2 เพื่อไม่สร้าง resource ซ้ำ
- Verification: backend tests 26/26 ผ่าน; frontend build ผ่าน (ยังมี Vite warning เรื่อง bundle >500 kB); การดึง Open-Meteo ตาม schedule จริงยังรอตรวจหลัง restart backend

### Phase 2:
1. **Contract + Order**: ระบบสัญญารายปีและคำสั่งซื้อ (พร้อมฟิลด์ `delivery_location` เพราะราคาส่งแต่ละพื้นที่ไม่เท่ากัน)
2. **Dashboard เปรียบเทียบรายได้ต่อลูกค้า**: วิเคราะห์ยอดและเปรียบเทียบสัดส่วนรายได้จากลูกค้าแต่ละราย
3. **StockItem (แบบเบา ๆ)**: จัดการของใช้แบบง่าย (ไม่มีคลังใหญ่ ซื้อเติมเมื่อใกล้หมด)
4. **Transaction & LaborLog**: การเงินจริงและบันทึกค่าแรงจ้างคนงานรายวัน
5. **Reports & Analytics**: จัดกลุ่มตามไตรมาส/ฤดู และแนวโน้มราคาตามช่วงเวลา/พื้นที่
6. **ช่องรอผลวิเคราะห์**: Phase 2 เดิมระบุ `Insight` แต่ Phase 1e เพิ่ม `Recommendation`; ก่อนเริ่ม Phase 2 ให้รวมเป็น resource เดียวแล้วจึงกำหนด endpoint/UI

### Phase 3: Infrastructure
- ทดสอบรันบน Raspberry Pi 4 (2GB) จริง
- ระบบสำรองฐานข้อมูลอัตโนมัติ (Automated backup สำหรับ `erp.db`)
- Deploy จริง พร้อมเชื่อมต่อ Cloudflare Tunnel

### Phase 4
- Flutter Mobile App และหน้า UI ส่วนเสริมที่เหลือ

### Phase 5 — AI (เริ่มหลัง Phase 4 เท่านั้น)
- ตัวเลือก: เตือนความเสี่ยงจากอากาศเชื่อม Task reminder, วางแผนแรงงานรายสัปดาห์ หรือ optimization การปลูก; ยังไม่มีการตัดสินใจเลือก
- ต้องรันบน Raspberry Pi 4 (2GB) ได้; ฝึกโมเดลนอกเครื่องและรัน inference เป็น batch job แยกจาก API

## สิ่งที่ต้องระวังด้าน Security และข้อมูล (จาก PROJECT_CONTEXT.md)

- **Role**: มี `owner` (เห็นข้อมูลจริงทั้งหมด) และ `developer` (ห้ามเห็นข้อมูลลับเป็น plaintext)
- **ข้อมูลที่ต้องปิดบังจาก Developer**: ชื่อลูกค้า, ข้อมูลติดต่อ, ยอดรายได้, ชื่อ/ปริมาณปุ๋ยและยา, note กิจกรรม และ title ของ manual Task; เข้ารหัสจริงใน DB และ developer เห็น ciphertext ที่ response boundary
- **นโยบายล่าสุด (MASKING_POLICY.md, 2026-11-01)**: ปิดข้อมูลคน, ชื่อปุ๋ย/ยา/ปุ๋ยผสม, free-text note, manual Task title และจำนวนเงินทุกชนิด; เปิด quantity/stock, category, unit, date, status, weather, crop cycle และ harvest quantity. ข้อที่ระบุ ◐/✖ ยังรอ owner ยืนยัน
- Phase 1e ยังเก็บ `InputItem.quantity` เป็น ciphertext อยู่; ต้องทำ decrypt/round-trip migration พร้อม D4 และเปลี่ยน API response ก่อน developer UI แสดงตัวเลขจริง. ระหว่างนี้ UI ต้องแสดงสถานะ masked โดยไม่เปิด ciphertext
- `unit`, `category`, วันที่, metadata ของ catalog และ Task อัตโนมัติยังเป็น plaintext. เงิน Phase 2 ต้องใช้ secure number helpers และคำนวณ aggregate ที่ backend หลัง decrypt
- ขอบเขตการป้องกันคือข้อมูลผ่านแอปพลิเคชัน; ผู้ที่เข้าถึง shell และ `ENCRYPTION_KEY` ได้ยังถอดรหัสได้; production key ต้องเป็นของเจ้าของฟาร์มและสำรองแยกจาก DB
- **ห้าม hardcode รายชื่อปุ๋ย/ยา/สูตรผสม** และ **ห้าม seed ตาราง `InputCatalog` ล่วงหน้า** (ต้องเกิดจากการกรอกจริง)

## ข้อควรระวังด้านข้อมูล

- API ควรส่งวันที่เป็น ISO format เช่น `2026-09-06` แล้วให้ frontend จัดรูปแบบตาม locale
- ต้องกำหนด mapping ระหว่างสถานะภาษาไทยใน UI กับ enum ภาษาอังกฤษใน backend
- ข้อมูลที่มีสิทธิ์จำกัด เช่น ชื่อลูกค้าและข้อมูลติดต่อ ควรถูกกรองที่ backend response boundary เสมอ ไม่ควรกรองเฉพาะใน frontend

## ไฟล์หลักที่เกี่ยวข้อง

- `app/routers/customers.py`
- `app/routers/crop_cycles.py`
- `app/routers/reference.py`
- `app/models.py`
- `app/schemas.py`
- `src/pages/FarmPlots.jsx`
- `src/pages/PlotDetail.jsx`
- `src/pages/Inventory.jsx`
- `src/pages/Sales.jsx`
- `src/components/Navbar.jsx`
- `src/components/DataTable.jsx`
- `src/data/mockData.js`
