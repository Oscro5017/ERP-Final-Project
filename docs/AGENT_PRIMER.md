# Agent Primer — ERP บ้านผักสดฟาร์ม (อ่านก่อนเริ่มงานทุกครั้ง)

> สรุปจากเอกสารโปรเจคและ audit (พ.ย. 2026) เพื่อให้ไม่ต้องสำรวจ repo ใหม่ทุกครั้ง
> **โค้ดจริงสำคัญกว่าเอกสารนี้** ถ้าพบว่าขัดกัน ให้รายงานข้อขัดแย้ง ห้ามเชื่อเอกสารเหนือโค้ด และชื่อฟังก์ชัน/ไฟล์ที่อ้างด้านล่างต้องตรวจจากโค้ดจริงก่อนใช้

## โปรเจค

ERP ฟาร์มไฮโดรโปนิกส์ของลูกค้าจริง (เจ้าของคนเดียว ใช้มือถือเป็นหลัก; นักพัฒนาดูผ่านคอม) เป็นโปรเจค capstone ทีม 2 คน กำหนดส่งโดยประมาณกลาง ม.ค. – ต้น ก.พ. 2027 จะรันบน Raspberry Pi 4 (RAM 2GB) ผ่าน Cloudflare Tunnel อาจารย์ที่ปรึกษากำหนด 4 module หลัก: **สินค้า, คลัง, รับเข้า, ส่งออก** และมีระบบเสริม: เก็บข้อมูลอากาศ/พยากรณ์ + คำแนะนำเชิงช่วงเวลา

## โครงสร้าง repo (monorepo)

| ที่ | คืออะไร |
|---|---|
| `app/` | backend FastAPI + SQLAlchemy 2 + SQLite: `main.py` (lifespan, scheduler, startup), `config.py`, `database.py` (PRAGMA WAL/FK), `models.py`, `schemas.py`, `security.py`, `migrations.py` (migration แบบ custom), `seed.py`, `logging_config.py`, `routers/`, `services/` (`secure_fields.py`, `encryption_canary.py`, `encrypted_data_audit.py`, `input_catalog.py`, `task_generator.py`, `weather.py` ฯลฯ) |
| `tests/` | pytest (ใช้ DB ชั่วคราวใน tests เท่านั้น) |
| `scripts/` | เครื่องมือ เช่น `check_decrypt.py` |
| `src/` | เว็บ React + Vite + Tailwind + Chart.js (build ไปที่ `frontend/` ซึ่ง FastAPI serve; `frontend/index.html` มีการแก้ด้วยมือ ห้ามเขียนทับ) |
| `mobile/` | แอป Flutter |
| `docs/` | เอกสาร: `MASKING_POLICY.md` คือแหล่งอ้างอิงเดียวว่าฟิลด์ไหนปิด/เปิด |
| `PROJECT_CONTEXT.md`, `PROJECT_STATUS.md` | เอกสารโปรเจค (แก้โดย agent เอกสารหรือผู้ใช้เท่านั้น) |

## คำสั่ง

- backend: `python -m venv .venv` → `pip install -r requirements.txt` → เทสต์ `python -m pytest -q` → รัน `python -m uvicorn app.main:app --port 8000` (ห้าม `--reload` บน Pi, ใช้ worker เดียว)
- เว็บ: `npm run build` (ระวังไม่เขียนทับ `frontend/index.html`; ถ้าต้องดูขนาดให้ใช้ `--outDir` นอก workspace)
- Flutter: `flutter analyze`, `flutter test` (ห้าม `flutter build/run` ใน agent)

## แบบแผนที่ต้องทำตาม

- **แถวข้อมูล:** `created_at`/`updated_at` + soft delete (`deleted_at`) ใช้ helper query ของแถวที่ยังไม่ถูกลบที่มีในโค้ด (ตรวจชื่อจริง) ห้ามลบแถวจริงผ่าน API
- **role:** `owner` เห็นข้อมูลจริง; `developer` เห็น ciphertext + `is_masked` (developer เขียนได้ แต่ response ถูก mask)
- **ฟิลด์เข้ารหัส:** ใช้ `services/secure_fields.py` เท่านั้น (ห้ามสร้าง crypto ใหม่); ข้อความใช้ helper ถอดรหัสแบบ safe; ตัวเลขเงินใช้ `encrypt_number` / `present_number` / `present_aggregate`; `name_hash` = HMAC แบบเดียวกับ `InputCatalog` (derive จาก key ปัจจุบัน)
- **ถอดรหัสล้มเหลว:** ห้ามให้ endpoint ล่ม: ใช้ฟิลด์ `decrypt_failed` + placeholder (ข้อความ) / `null` (ตัวเลข ห้ามแทนด้วย 0) และ log ระดับ ERROR เฉพาะตาราง/id/ชนิดข้อผิดพลาด (ห้ามมี token หรือเนื้อหา)
- **ค้น/กรองฟิลด์ที่เข้ารหัส:** ถอดรหัสที่ backend แล้วกรองในหน่วยความจำ (ข้อมูลน้อย) ห้ามใช้ SQL กับฟิลด์เข้ารหัส
- **จำนวนเงิน:** คำนวณ/รวมที่ชั้น service ใน Python เท่านั้น **ห้าม SQL `SUM`/`GROUP BY` กับฟิลด์เงิน** ส่วนปริมาณ/สต็อกเป็น plaintext ใช้ SQL ได้
- **นโยบาย masking:** ปิด = ข้อมูลคน, ชื่อปุ๋ย/ยา/ปุ๋ยผสม, note, manual Task title, จำนวนเงิน; เปิด = ปริมาณ, ยอดคงเหลือ, `category`, หน่วย, วันที่, อากาศ, รอบปลูก (รายละเอียดใน `docs/MASKING_POLICY.md`)
- **migration:** เพิ่มใน `migrations.py` แบบ idempotent; ตารางใหม่แบบ additive ไม่ต้อง backup; การแก้ข้อมูลเดิมต้องใช้ `BACKUP_DIR` (ปฏิเสธถ้าไม่ตั้ง) + ตรวจ round-trip และ **ห้ามรันกับ DB จริงเอง**
- **SQLite:** `foreign_keys=ON`, WAL, `busy_timeout` ตั้งในทุก connection ระวัง `database is locked`
- **ข้อมูล dev:** ใช้ข้อมูลสมมติเท่านั้น; ห้ามใส่รายชื่อปุ๋ย/ยา/สูตรจริงในโค้ดหรือ seed; ห้ามตั้งหรือสร้าง `ENCRYPTION_KEY` ชั่วคราว (ใช้ key ใน `.env` ของผู้ใช้ หรือ key ใน fixture ของเทสต์)
- **ระบบเริ่มต้น:** มี key canary ใน `system_meta` — ถ้า key ไม่ตรงกับข้อมูล production จะไม่สตาร์ท

## กติกาการทำงานของ agent

- ทำงานใน branch ที่ผู้ใช้ระบุเท่านั้น ถ้าไม่ใช่ **หยุดและบอก**; **ห้าม commit / push / switch branch เอง**
- ห้ามอ่านหรือพิมพ์ `.env` และข้อมูลแถวใน DB จริง/สำเนา; ห้ามพิมพ์ secret หรือข้อมูลลับ
- ห้ามลบหรือแก้เทสต์เดิมเพื่อให้ผ่าน เพิ่มเทสต์ใหม่แทน; รัน `python -m pytest -q` และรายงานผลจริง (ถ้ารันไม่ได้ ให้บอกและให้คำสั่งที่ผู้ใช้ต้องรัน)
- แก้เฉพาะไฟล์ในขอบเขตที่ระบุใน prompt; ห้ามรีแฟกเตอร์ที่ไม่เกี่ยว; ห้ามแตะ `PROJECT_STATUS.md`, `PROJECT_CONTEXT.md`, `docs/` ยกเว้นงานเอกสารโดยตรง
- ทุกข้อสรุปเกี่ยวกับโค้ดต้องมีหลักฐาน `path:บรรทัด` ห้ามเดา ถ้าโค้ดจริงทำให้ข้อกำหนดของงานทำไม่ได้หรือขัดแบบแผนข้างบน **หยุดและรายงานก่อนแก้** ห้ามเปลี่ยนการตัดสินใจเอง

## รูปแบบรายงานท้ายงาน (สั้น)

ตารางเดียว: ข้อ → ผล → ไฟล์ที่แก้ (จัดกลุ่มตามข้อ) → เทสต์ที่เพิ่ม → ผล pytest จริง → สิ่งที่ผู้ใช้ต้องทำเอง → ความเสี่ยงที่เหลือ และปิดท้ายด้วย **รายการไฟล์ที่เปลี่ยนทั้งหมด** จาก `git status --short` ห้ามรายงานยาวหรือแปะโค้ดทั้งไฟล์
