# Prompt: ERP ฟาร์มผักออร์แกนิค — Phase 1d: Security Alignment

> ก่อนเริ่ม ให้อ่าน `PROJECT_CONTEXT.md` ที่ root ของโปรเจกต์ โดยเฉพาะหัวข้อ "Requirement ด้าน security/privacy" และ "กับดักที่เคยเกิดขึ้นแล้ว" และไฟล์นี้ต้องอยู่ที่ `Project-Phase/erp-farm-phase1d-security-alignment-prompt.md`
>
> งานนี้ต้องทำ **ก่อน Phase 2** เพราะยอดรายได้ใน Phase 2 จะใช้รูปแบบเดียวกัน ห้ามเริ่มสร้างตาราง Contract/Order/Transaction ในรอบนี้

## บริบทและช่องว่างที่ตรวจพบ
Requirement จริงคือ: ข้อมูล **ชื่อลูกค้า, ข้อมูลติดต่อลูกค้า, ยอดรายได้** ต้องเข้ารหัสจริงใน database และ role `developer` ต้องเห็นเป็น **ciphertext** (ข้อความเข้ารหัสอ่านไม่ออก) ไม่ใช่ถูกซ่อนไปเลย ส่วน role `owner` เห็นค่าจริง

สถานะปัจจุบัน (ตาม `PROJECT_STATUS.md`) ที่ยังไม่ตรง:
1. `Customer.contact` เก็บเป็นข้อความธรรมดาใน DB
2. developer เห็น `ID #...` แทนชื่อ และเห็น contact ว่างเปล่า — ควรเป็น ciphertext
3. ยังไม่มีรูปแบบกลางสำหรับข้อมูลลับตัวเลข (รายได้) ที่ Phase 2 จะต้องใช้

---

## งานที่ 1: เข้ารหัส Customer.contact พร้อม migrate ข้อมูลเดิม

1. เพิ่มคอลัมน์ `contact_encrypted` (เก็บ Fernet token) ใน `Customer`
2. เขียน migration (ใน `app/migrations.py` ตามแบบที่ทำไว้) ที่:
   - **สำรอง DB ก่อนเสมอ** (หรือเช็คว่ามี backup ล่าสุดแล้ว) ห้ามรัน migration ถ้าสำรองไม่สำเร็จ
   - อ่านค่า `contact` เดิมแต่ละแถว เข้ารหัสแล้วเขียนลง `contact_encrypted`
   - **ตรวจ round-trip**: ถอดรหัสกลับแล้วต้องเท่ากับค่าเดิมทุกแถว ถ้ามีแถวใดไม่ตรงให้หยุดและ log แถวนั้น ห้ามไปขั้นต่อไป
   - เมื่อตรวจผ่านครบ จึงล้างค่า plaintext ในคอลัมน์ `contact` เดิม (ตั้งเป็น NULL หรือ rebuild ตารางโดยตัดคอลัมน์ออก) ห้ามทิ้ง plaintext ไว้
   - รันซ้ำได้อย่างปลอดภัย (idempotent) และ log จำนวนแถวที่แปลง
3. `POST /customers` ต้องเข้ารหัส contact ก่อนบันทึกเสมอ
4. ถ้า `ENCRYPTION_KEY` ไม่ถูกตั้งหรือผิดรูปแบบ ให้ backend ล้มเหลวตอน startup พร้อมข้อความชัดเจน (ไม่ใช่เงียบแล้วเก็บ plaintext)

## งานที่ 2: Developer เห็น ciphertext

1. สร้างโมดูลกลาง เช่น `app/services/secure_fields.py` มีฟังก์ชัน:
   - `encrypt_text(plain) -> token`, `decrypt_text(token) -> plain`
   - `present_text(token, role)` → owner ได้ค่าถอดรหัสแล้ว, developer ได้ token เดิมโดย **ไม่ถอดรหัส**
2. แก้ `app/routers/customers.py` และ schema ให้ใช้ `present_text` กับ `name` และ `contact` ทั้งคู่ โดย response ต้องมี `id` และฟิลด์ `is_masked` (bool) ด้วย
3. เลิกใช้รูปแบบ `ID #...` แทนชื่อ และเลิกคืน contact ว่างให้ developer
4. Frontend (Customer panel): ถ้า `is_masked = true` ให้แสดง ciphertext แบบตัดให้สั้น (เช่น 24 ตัวอักษรแรก + "…") ใช้ฟอนต์ monospace สีจาง และมี tooltip/ปุ่มคัดลอกค่าเต็มได้ ส่วน owner แสดงค่าจริงตามเดิม
5. การค้นหาชื่อลูกค้า: Fernet ไม่ deterministic จึงค้นใน SQL ไม่ได้ ให้ owner ค้นโดยถอดรหัสใน backend แล้วกรองในหน่วยความจำ (ข้อมูลหลักร้อย–พันแถวรับได้) ส่วน developer ไม่ต้องรองรับการค้นชื่อ

## งานที่ 3: วางรูปแบบสำหรับข้อมูลลับตัวเลข (ใช้กับรายได้ใน Phase 2)

ยังไม่ต้องสร้างตารางรายได้ ให้เตรียมแค่ helper และกติกา:

1. เพิ่มใน `secure_fields.py`: `encrypt_number(value) -> token` (เก็บเป็น Fernet token ของสตริงตัวเลขแบบ Decimal) และ `decrypt_number(token) -> Decimal`
2. เพิ่ม `present_number(token, role)` เหมือน `present_text`
3. เพิ่ม `present_aggregate(value, role)` สำหรับผลรวม/สถิติที่คำนวณจากตัวเลขลับ: เซิร์ฟเวอร์รวมค่าหลังถอดรหัส แล้ว owner ได้ตัวเลขจริง ส่วน developer ได้ **Fernet token ของผลลัพธ์นั้นที่เข้ารหัสใหม่** พร้อม `is_masked: true` (ห้ามส่งตัวเลขจริงหรือค่าประมาณไป)
4. กติกาที่ Phase 2 ต้องทำตาม: ยอดรายได้ทุกตัวเก็บเป็น token ใน DB, การรวม/จัดกลุ่มตามไตรมาสหรือลูกค้าทำที่ backend หลังถอดรหัส (SQL `SUM`/`GROUP BY` บนคอลัมน์ที่เข้ารหัสใช้ไม่ได้), กราฟของ developer แสดงเป็นกล่องสถานะ "ข้อมูลเข้ารหัส" แทนกราฟจริง
5. เขียน unit tests ของ helper ด้วยตัวเลขสมมติ (ไม่ผูกกับตารางจริง)

## งานที่ 4: ตรวจรั่วไหลและการจัดการ key

1. ตรวจว่า log, ข้อความ error, ตัวอย่างใน `/docs`, ไฟล์ seed และ tests **ไม่มีข้อมูลลูกค้าจริง** (ใช้ชื่อ/เบอร์สมมติเท่านั้น)
2. ตรวจ `.gitignore` ให้ครอบคลุม `.env`, `erp.db` และไฟล์สำรอง `*.db` ทั้งหมด รวมถึง `erp-pre-phase1c-*.db`
3. **ไฟล์สำรองก่อน migration นี้ยังมี contact เป็น plaintext** ให้ระบุใน `PROJECT_STATUS.md` ว่าไฟล์สำรองเก่าต้องเก็บไว้กับเจ้าของฟาร์มหรือที่ปลอดภัย ห้ามอยู่ใน repo และห้ามส่งให้ทีมพัฒนา
4. เพิ่มหมายเหตุใน `.env.example` ว่า: `ENCRYPTION_KEY` ของ production เจ้าของฟาร์มเป็นคนตั้งและเก็บเอง (และต้องสำรอง key ไว้ที่ปลอดภัยแยกต่างหาก เพราะ key หาย = ข้อมูลที่เข้ารหัสอ่านไม่ได้ถาวร) ส่วน environment พัฒนาต้องใช้ key คนละตัวกับข้อมูลสมมติเท่านั้น
5. (ไม่ต้องทำรอบนี้ แต่ให้ใช้ `MultiFernet` ถ้าไม่ยุ่งยาก เพื่อรองรับการหมุน key ในอนาคต)

## งานที่ 5: เก็บกวาดเอกสารสถานะ

แก้ `PROJECT_STATUS.md` ให้ตรงกัน:
- ส่วน Weather/API ที่ยังเขียนว่า sync เวลา 06:00 → แก้เป็น 08:00 (Asia/Bangkok) ตามที่ตั้งค่าจริง
- บรรทัด "พิกัดฟาร์มยังเป็นค่า default และยังต้องยืนยันกับเจ้าของ" ในส่วน Weather → แก้ให้ตรงกับที่ยืนยันแล้ว
- หัวข้อที่ยังมีคำว่า "backend implementation มีแล้ว" ให้ปรับเป็นสถานะปัจจุบัน
- อัปเดตตาราง Roadmap/Phase ให้ตรงกับ `PROJECT_CONTEXT.md` (Phase 1c เสร็จ, Phase 1d, Phase 5)
- ลบหัวข้อ "Security follow-up" ออกเมื่อทำเสร็จจริง

---

## Acceptance criteria

- [ ] เปิดไฟล์ DB ตรง ๆ (เช่น `sqlite3`) แล้ว `Customer` ไม่มีข้อความ contact หรือชื่อแบบอ่านออกในคอลัมน์ใด ๆ
- [ ] สร้างลูกค้าทดสอบด้วยเบอร์สมมติที่รู้ค่า แล้วค้นหาค่านั้นในไฟล์ `erp.db` (เช่น ด้วย `strings`) ต้องไม่เจอ
- [ ] Login owner → เห็นชื่อและ contact จริงของลูกค้าเดิมครบทุกราย ไม่มีรายใดหายหรือเพี้ยน
- [ ] Login developer → เห็นชื่อและ contact เป็น ciphertext (ขึ้นต้นแบบ Fernet `gAAAA...`), ไม่มี `ID #...`, มี `is_masked: true` และ UI แสดงแบบตัดสั้น + คัดลอกได้
- [ ] Migration รันซ้ำแล้วไม่เกิดข้อมูลซ้ำหรือเสียหาย และหยุดทันทีถ้าตรวจ round-trip ไม่ผ่าน
- [ ] ตั้ง `ENCRYPTION_KEY` ผิดหรือไม่ตั้ง → backend แจ้ง error ตอน startup
- [ ] Soft delete ของ Customer และ masking เดิมของส่วนอื่นยังทำงานปกติ
- [ ] tests ใหม่ผ่าน: round-trip migration, owner vs developer ของ customers, helper `present_text`/`present_number`/`present_aggregate`
- [ ] `PROJECT_STATUS.md` ไม่มีข้อความขัดกันเรื่องเวลา sync และพิกัดแล้ว

## ขอบเขตที่ห้ามแตะในรอบนี้

- ห้ามสร้าง Contract/Order/Transaction/รายได้จริง (เป็นงาน Phase 2)
- ห้ามเปลี่ยนสิทธิ์ของข้อมูลปุ๋ย/ยา (InputApplication/InputItem/InputCatalog ยังเปิดให้ developer เห็นตามเดิม)
- ห้ามสร้างตาราง `Insight` หรือส่วน AI
- หลังทำเสร็จ ให้อัปเดตสถานะในตาราง index ของ `PROJECT_CONTEXT.md` และ `PROJECT_STATUS.md`
