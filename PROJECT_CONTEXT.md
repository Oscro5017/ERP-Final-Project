# PROJECT_CONTEXT.md — บริบทและ Requirement จริงของ ERP ฟาร์มผักออร์แกนิค

> **อ่านไฟล์นี้ก่อนเสนอ "งานที่ควรทำต่อ" ทุกครั้ง** — ห้ามอ้างอิงจากโครง UI ที่มีอยู่แล้ว (เช่นหน้า Inventory/Sales/Reports ใน `code_prototype`) มาเป็นตัวกำหนดลำดับความสำคัญ เพราะหน้าพวกนี้เป็นแค่ template ที่ยกมาทั้งชุด ไม่ได้แปลว่ามันสำคัญกว่าสิ่งที่เจ้าของฟาร์มขอจริง `PROJECT_STATUS.md` บอกแค่ว่า "ทำอะไรไปแล้ว" ส่วนไฟล์นี้บอกว่า "ทำไมต้องทำแบบนี้ และอะไรควรทำก่อน-หลัง"

## ไฟล์ spec รายเฟส (ต้องเปิดอ่านทั้งไฟล์ก่อนเริ่มงานเฟสนั้นเสมอ)

ทุกเฟสมี spec ละเอียดเป็นไฟล์แยก เก็บไว้ที่ `docs/phases/` ในโปรเจกต์นี้ — ไฟล์พวกนี้มีรายละเอียด data model, endpoint, logic เฉพาะ, และ acceptance criteria ที่ `PROJECT_STATUS.md` และไฟล์นี้สรุปมาแค่หัวข้อเท่านั้น **ห้ามเริ่มเขียนโค้ดของเฟสไหนโดยไม่เปิดอ่านไฟล์ spec ของเฟสนั้นก่อน**

| ไฟล์ | เฟส | สถานะ |
|---|---|---|
| `docs/phases/phase-0-foundation.md` | แก้ status enum 5 ค่า, cycle_code, เชื่อม Farm Plots↔CropCycle, 401 handler | ✅ เสร็จแล้ว |
| `docs/phases/phase-1-input-application.md` | InputApplication + InputItem + InputCatalog autocomplete | ✅ เสร็จแล้ว |
| `docs/phases/phase-1b-task-weather.md` | Task reminder + WeatherLog | 🟡 implementation เสร็จ; พิกัดยืนยันแล้ว, รอตรวจ scheduled sync ใน environment จริง |
| `docs/phases/phase-1c-chartjs-and-data-hooks.md` | ย้ายกราฟไป Chart.js + เก็บข้อมูลที่ AI จะใช้ในอนาคต (ผลผลิต, status log, timestamps/soft delete) | ✅ implementation เสร็จ; tests/build ผ่าน |
| `docs/phases/phase-1d-security-alignment.md` | เข้ารหัสข้อมูลลูกค้า, แสดง ciphertext ตาม role, เตรียม helper ตัวเลขลับ | ✅ implementation และ migration เสร็จ; tests ผ่าน |
| `docs/phases/phase-1e-input-masking-data-hooks.md` | เข้ารหัสข้อมูลปุ๋ย/กิจกรรม, manual task, forecast snapshots, sensor readings และ recommendation data hooks | ✅ implementation, live migration, tests/build ผ่าน |

> เมื่อได้รับ spec ไฟล์ใหม่ของเฟสถัดไป ให้ **บันทึกไฟล์นั้นลง `docs/phases/` ในโปรเจกต์จริงทันที** (ไม่ใช่แค่ทำตามแล้วทิ้ง) แล้วเพิ่มแถวใหม่ในตารางนี้ พร้อมอัปเดตสถานะในตารางนี้ทุกครั้งที่ทำเฟสไหนเสร็จ

## บริบทลูกค้า
ระบบนี้ทำให้ลูกค้าจริง — ฟาร์มไฮโดรโปนิกส์ชื่อ "บ้านผักสดฟาร์ม" ผู้ใช้งานหลักมีแค่เจ้าของฟาร์มคนเดียว (ไม่มีพนักงานประจำ จ้างเฉพาะช่วงต้องใช้คน) requirement ทั้งหมดด้านล่างมาจากการสัมภาษณ์เจ้าของฟาร์มโดยตรง 2 รอบ

## ข้อเท็จจริงเกี่ยวกับการทำฟาร์ม (ต้องยึดตามนี้เวลาออกแบบ logic)

- ปลูกแบบไฮโดรโปนิกส์บนโต๊ะ 49 ตัว ให้น้ำไหลผ่านตลอด ไม่ใช้ดิน
- แบ่งปลูก 8 ชุด เหลื่อมกันชุดละ 1 สัปดาห์
- ปลูก 3 พันธุ์: กรีนโอ๊ค, เรดโอ๊ค, ฟิลเลย์
- เพาะเมล็ดปกติทุกวันอังคาร แต่ขยับได้ถ้าไม่สะดวก (อย่า hardcode ตายตัว)
- ผลิตต่อเนื่องทั้งปี ยกเว้นมีโรคระบาด
- **สถานะการปลูกมีแค่ 5 ขั้น**: อนุบาล → สร้างพุ่ม → พร้อมเก็บเกี่ยว → เก็บเกี่ยว → ว่าง — การให้ปุ๋ย/พ่นยา **ไม่ใช่สถานะ** เป็นกิจกรรมแยกที่เกิดได้ทุกช่วง (ดูโมดูล InputApplication)
- ปุ๋ย/ยาผสมหลายชนิดต่อครั้ง ปริมาณไม่คงที่ ปรับตามสภาพแวดล้อม — ห้ามมี list ตายตัว/hardcode ชื่อปุ๋ยในโค้ด
- ไม่มีคลังใหญ่ เก็บของแค่ถุง/กระสอบไม่กี่ใบ ซื้อเติมเมื่อใกล้หมด
- รับออร์เดอร์แบบสัญญารายปี (ลูกค้าประจำ ส่งต่อเนื่อง) + มีขายปุ๋ยผสมด้วย
- ราคาส่งออกไม่เท่ากันในแต่ละพื้นที่ (`delivery_location` ต้องเป็น field แยก ไม่ผูกราคาคงที่กับสินค้า)
- อยากดูข้อมูลย้อนหลังได้ครบถ้วน ทุกโมดูลควรเก็บประวัติ ไม่ใช่แค่ค่าปัจจุบัน

## สิ่งที่เจ้าของฟาร์มขอโดยตรง (เรียงตามที่พูดย้ำ/ให้น้ำหนัก)

1. ระบบพยากรณ์/คาดคะเนสภาพอากาศแบบละเอียด (พูดย้ำ 2 รอบ)
2. ระบบแจ้งเตือนงานที่ต้องทำ — "บางทีลืม"
3. ระบบเปรียบเทียบรายได้จากลูกค้าแต่ละราย
4. ความสามารถเพิ่ม/ลบข้อมูลเองได้อิสระในหลายส่วน (ส่วนหนึ่งเพราะไม่อยากเปิดเผยสูตร/ข้อมูลให้ทีมพัฒนาเห็น)
5. วิเคราะห์แนวโน้มราคาของแต่ละช่วงเวลา/พื้นที่
6. คำนวณต้นทุน-รายรับ-รายจ่าย-กำไร/ขาดทุน

**มิติที่เจ้าของฟาร์มให้ความสำคัญเป็นพิเศษ** (ต้องมีใน report/dashboard ทุกตัวที่เกี่ยวข้อง): ไตรมาส, สภาพอากาศ, ช่วงเวลา, ฤดู, ราคาแต่ละช่วง, ราคาแต่ละพื้นที่, อุณหภูมิ, ค่าแรงงาน+งานที่คนงานต้องทำ

## Requirement ด้าน security/privacy (สำคัญ — เข้าใจผิดบ่อย)

- Role มี 2 แบบ: `owner` (เห็นทุกอย่างจริง) และ `developer` (เข้าใช้เพื่อดูแล/ปรับปรุงระบบ แต่ห้ามเห็นข้อมูลลับเป็น plaintext)
- ข้อมูลที่ต้องปิดบังจาก developer: **ชื่อลูกค้า, ข้อมูลติดต่อลูกค้า, ยอดรายได้, ชื่อและปริมาณปุ๋ย/ยา, note กิจกรรม และชื่องานที่ owner บันทึกเอง**
- ตาม `MASKING_POLICY.md` (2026-11-01): ปิดข้อมูลคน, ชื่อปุ๋ย/ยา/ปุ๋ยผสม, free-text note, manual Task title และจำนวนเงินทุกชนิด; เปิด quantity/stock, category, unit, date, status, weather, crop cycle และ harvest quantity. รายละเอียดบางข้อเป็นมติทีมรอยืนยันจาก owner.
- วิธีปิดบัง: เข้ารหัสจริงที่ database (ไม่ใช่แค่ mask ตอน response) แล้ว developer เห็น ciphertext ตรง ๆ ไม่ decrypt ให้
- สถานะ implementation: Phase 1e เข้ารหัส `InputItem.item_name`, `InputItem.quantity`, `InputApplication.note`, `InputCatalog` name และ manual Task title ด้วย Fernet. Policy ล่าสุดกำหนดให้ quantity เปิด; ต้องถอดรหัส/migrate พร้อม D4 ที่ผูก input กับ `product_id` และปรับ response API ก่อน UI จะแสดง quantity ต่อ developer. จน migration ผ่านให้ถือ quantity response เป็น masked และห้าม render ciphertext เป็นตัวเลข.
- `unit`, `category`, วันที่, task อัตโนมัติ และ metadata ของ catalog เป็น plaintext; ตัวเลขเงินใน Phase 2 ใช้ `encrypt_number`/`present_number`/`present_aggregate` และ aggregate ต้องคำนวณที่ backend หลัง decrypt.
- Developer ยังสร้าง/แก้ข้อมูลปุ๋ย/ยาได้ แต่ API ต้องตอบ ciphertext พร้อม `is_masked`; catalog suggestions ของ developer เป็น list ว่าง
- การป้องกันนี้มีขอบเขตที่ application/database เท่านั้น ผู้ที่เข้าถึง shell และ `ENCRYPTION_KEY` ได้ยังถอดรหัสข้อมูลได้; production key ต้องเป็นของเจ้าของฟาร์มและสำรองแยกจากฐานข้อมูล

## Roadmap เต็ม (ลำดับนี้คือของจริง ยึดตามนี้เสมอ)

แผนรวม: ไล่ทำตามลำดับด้านล่างจนจบ Phase 4 ก่อน แล้วค่อยทำส่วน AI (Phase 5) โดยระหว่างทางต้อง **เปิด "ช่องรอ" สำหรับ AI ไว้** (ดูหัวข้อ "ช่องรอ AI" ด้านล่าง) เพื่อไม่ต้องรื้อระบบทีหลัง

**Phase 0 — ✅ เสร็จแล้ว**: แก้ status enum เป็น 5 ค่า, เพิ่ม `cycle_code`, เชื่อม Farm Plots↔CropCycle จริง, global 401 handler

**Phase 1 — ✅ เสร็จแล้ว**: InputApplication + InputItem + InputCatalog (autocomplete บันทึกปุ๋ย/ยา)

**Phase 1b — implementation เสร็จ; รอยืนยันภายนอก**:
- Task reminder ผูกกับ CropCycle, Dashboard widget และหน้า Activities ที่ใช้ Task API จริง
- WeatherLog, forecast widget และ scheduled upsert job
- ฟอร์ม CropCycle ใช้วันอังคารถัดไปเป็นค่าเริ่มต้น แต่ยังแก้วันได้
- เจ้าของยืนยันพิกัดจุดกึ่งกลางฟาร์มแล้ว (18.8072866, 99.0930437); ตั้งเวลาซิงก์เป็น 08:00 `Asia/Bangkok`
- ยังต้องตรวจ scheduled weather sync กับ Open-Meteo บน environment จริงหลัง restart backend

**Phase 1c — ✅ implementation เสร็จ**:
- ย้ายกราฟที่มีอยู่จาก Recharts ไป Chart.js ผ่าน shared wrappers; Recharts ถูกถอนออกแล้ว
- เพิ่ม `harvest_quantity_kg`, `CropCycleStatusLog`, timestamps และ soft delete พร้อม migration/backfill
- Backend tests 10/10 ผ่าน, frontend build ผ่าน; ฐานข้อมูลเดิมถูก migrate หลังสำรองข้อมูล

**Phase 1d — ✅ เสร็จแล้ว**: เข้ารหัสชื่อลูกค้าและข้อมูลติดต่อ พร้อมแยก response ตาม role และ helper สำหรับข้อมูลตัวเลขลับ

**Phase 1e — ✅ implementation และ migration เสร็จ**:
- implementation เดิมเข้ารหัสชื่อ/ปริมาณ input, note และ manual task title; developer ได้ ciphertext, owner ได้ plaintext. **Policy 2026-11-01 เปลี่ยน quantity เป็นข้อมูลเปิด**; ต้อง migrate quantity และ response API พร้อม D4 ก่อนเปิดให้ developer; ปัจจุบันยังห้ามแสดง token quantity ใน UI
- Catalog ใช้ HMAC-SHA256 ที่ derive จาก Fernet key; suggestions ของ developer ว่าง
- เก็บ ForecastSnapshot รายวัน, catch-up WeatherLog ย้อนหลังแบบ background, sensor ingestion ใช้ `X-Device-Token`
- เพิ่มตารางว่าง `Recommendation`; ยังไม่มี rule engine, API หรือ UI
- Migration สำรองนอก repo พร้อมจำกัด ACL, ตรวจ round-trip และ integrity; tests/build ผ่าน

**Phase 2 — backend implementation เสร็จบน `backend/products-stock`; ตรวจส่งมอบต่อใน `docs/phases/phase2/PROGRESS.md`**:
- Contract + Order (พร้อม `delivery_location`)
- Dashboard เปรียบเทียบรายได้ต่อลูกค้า
- StockItem แบบเบา ๆ
- Transaction (การเงินจริง)
- LaborLog (ค่าแรงจ้างรายวัน — ต้องเก็บ `worker_count` + ชั่วโมงทำงาน + ประเภทงาน ไม่ใช่แค่ยอดเงิน)
- Reports: group by ไตรมาส/ฤดู, แนวโน้มราคาตามช่วง/พื้นที่
- ช่องรับผลวิเคราะห์: Phase 2 รวม `Insight` กับ `Recommendation` เป็น resource เดียวแบบ additive; API/schema อยู่ใน `docs/API_PHASE2.md` และ `docs/openapi.phase2.json`

**Phase 3 — Infrastructure**: ทดสอบ Raspberry Pi 4 (2GB) จริง, backup อัตโนมัติของ `erp.db`, deploy จริง + Cloudflare Tunnel

**Phase 4**: Flutter mobile app, Reports/Users/Settings UI ที่เหลือ

**Phase 5 — AI (ทำหลัง Phase 4 เท่านั้น ยังไม่ต้องเริ่ม)**: ตัวเลือกที่คุยกับอาจารย์ที่ปรึกษา (ยังไม่ได้ตัดสินใจเลือก) — เตือนความเสี่ยงจากอากาศเชื่อม Task reminder / วางแผนแรงงานรายสัปดาห์ / ตัวช่วยวางแผนการปลูก (optimization) ข้อจำกัด: ต้องรันบน Pi 4 2GB ได้ (ฝึกโมเดลนอกเครื่อง, รัน inference เป็น batch job แยกจากโปรเซส API)

## ช่องรอ AI (ทำแทรกในแต่ละ phase ตามด้านบน ไม่ต้องรอ Phase 5)

- เก็บข้อมูลที่โมเดลจะใช้เทียบผลจริงตั้งแต่ตอนนี้ (ผลผลิตต่อรอบ, ประวัติเปลี่ยนสถานะ, ชั่วโมง/จำนวนคนงาน, timestamps) — ข้อมูลที่ไม่เก็บตั้งแต่ต้นจะหายถาวร
- ผลลัพธ์คำแนะนำ/insight ในอนาคตต้องใช้ resource เดียว (ตัดสินชื่อ `Insight` หรือ `Recommendation` ก่อน Phase 2) พร้อม source/version metadata; ห้ามสร้างตารางหรือ endpoint ซ้ำซ้อน
- ผลของ insight ที่เกี่ยวกับ Customer/รายได้ ต้องผ่านการ mask ตาม role เหมือนข้อมูลเดิม ห้ามหลุดไปทางหน้า insight
- ห้ามเรียกกฎง่าย ๆ ว่า AI/ML ในเอกสารหรือ UI — ให้ระบุว่าเป็น rule-based

## การตัดสินใจด้านเทคโนโลยีที่ล็อกแล้ว

- **ไลบรารีกราฟคือ Chart.js** (ผ่าน `react-chartjs-2`) เพราะเอกสารโปรเจคระบุไว้แบบนี้ — กราฟใหม่ทุกตัวต้องใช้ Chart.js และห้ามเพิ่มกราฟด้วย Recharts อีก (ของเดิมจะถูกย้ายใน Phase 1c)

## ⚠️ กับดักที่เคยเกิดขึ้นแล้ว (อย่าทำซ้ำ)

- **อย่าเสนอ Inventory/Sales/Costs/Reports/Navbar search/notification ก่อน Task reminder และ WeatherLog** — เคยเกิดขึ้นแล้วที่ agent เสนอลำดับงานโดยอ้างอิงจากหน้า UI ที่มีอยู่ (จาก `code_prototype`) แทนที่จะอ้างอิงจาก requirement จริงในไฟล์นี้ หน้าที่มี UI อยู่แล้วไม่ได้แปลว่าต้องทำต่อก่อน
- **อย่าใช้ 6 สถานะเดิม** (`fertilizing`, `treating` เป็นสถานะ) — แก้ไปแล้วใน Phase 0 อย่าเผลอ revert
- **อย่า hardcode รายชื่อปุ๋ย/ยา/สูตรผสมไว้ในโค้ดหรือ dropdown** — ต้องเป็น free text + autocomplete จากประวัติเท่านั้น
- **อย่า seed ข้อมูลล่วงหน้าใน `InputCatalog`** — ต้องเกิดจากการใช้งานจริงเท่านั้น
- ก่อนเสนอ "ลำดับงานที่แนะนำ" ใน `PROJECT_STATUS.md` ทุกครั้ง ให้เทียบกับ Roadmap ในไฟล์นี้ก่อนเสมอ ถ้าจะเสนอนอกลำดับ ต้องระบุเหตุผลชัดเจนว่าทำไมถึงควรสลับ ไม่ใช่เสนอเงียบ ๆ ตามโครง UI ที่มีอยู่
- **อย่าเพิ่มกราฟด้วย Recharts** — โปรเจคตกลงใช้ Chart.js แล้ว
- **อย่าเรียกฟีเจอร์ที่เป็นกฎธรรมดาว่า AI/ML** และอย่าเริ่มทำ Phase 5 ก่อน Phase 4 จบ
