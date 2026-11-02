# Prompt: ERP ฟาร์มผักออร์แกนิค — Phase 0 (แก้ฐานรากให้ถูกต้องก่อนต่อยอด)

## บริบท
โปรเจกต์ `ERPOganicFarm` (FastAPI + SQLAlchemy backend, React/Vite frontend) มี Auth, Customer masking, และ CropCycle API ทำงานได้แล้วบางส่วน แต่พบว่า **สถานะการปลูกในโค้ดปัจจุบันไม่ตรงกับกระบวนการจริงของฟาร์ม** และหน้า Farm Plots ยังเป็น mock data แยกจาก CropCycle API จริง งานรอบนี้คือแก้ 4 จุดนี้ให้เสร็จเป็นชุดเดียวก่อนเริ่มฟีเจอร์ใหม่ใด ๆ

**ห้ามเริ่มทำโมดูลใหม่ (Inventory, Sales, Costs, Reports ฯลฯ) ในรอบนี้ — โฟกัสแค่ 4 งานด้านล่างเท่านั้น**

---

## งานที่ 1: แก้ status enum ของ CropCycle

### ปัญหา
`app/models.py` ปัจจุบันใช้สถานะ 6 ค่า: `nursery, transplanted, fertilizing, treating, harvested, cleaning`

### สถานะที่ถูกต้อง (ยืนยันจากเจ้าของฟาร์มโดยตรง) — มีแค่ 5 ค่า
```
nursery          -> อนุบาล (รอต้นยืนต้นได้)
bushed           -> สร้างพุ่ม (เอาต้นลงปลูก)
ready_to_harvest -> พร้อมเก็บเกี่ยว
harvested        -> เก็บเกี่ยว
empty            -> ว่าง (พักโต๊ะ / รอทำความสะอาด)
```

**สำคัญ**: `fertilizing` และ `treating` (ให้ปุ๋ย/ใส่ยา) **ไม่ใช่สถานะ** — เป็นกิจกรรมที่เกิดขึ้นได้ทุกช่วงสถานะ ต้องบันทึกแยกเป็นโมดูล InputApplication ในอนาคต (ยังไม่ต้องสร้างตอนนี้ แค่เอา `fertilizing`/`treating` ออกจาก enum พอ)

### สิ่งที่ต้องทำ
1. แก้ enum/constraint ของ `CropCycle.status` ใน `app/models.py` ให้เหลือ 5 ค่าตามข้างบน
2. เพิ่ม field ใหม่ `cycle_code` (string) ใน `CropCycle` — generate อัตโนมัติจากวันที่เริ่มอนุบาล (`nursery_start`) รูปแบบ `YYMMDD` เช่น วันที่ 10/7/2026 → `260710`
3. เขียน migration script (หรือ manual ALTER ถ้ายังไม่ใช้ Alembic) เพื่ออัปเดต DB เดิมที่มีข้อมูลอยู่แล้ว — **ห้ามลบข้อมูลเดิม** แค่ map ค่า status เก่าไปค่าใหม่ที่ใกล้เคียงที่สุด (เช่น `fertilizing`/`treating` → เดาว่าใกล้เคียง `bushed` หรือ `ready_to_harvest` ตามวันที่ ถ้าไม่แน่ใจให้ log ออกมาให้เจ้าของฟาร์มเช็คทีหลัง ไม่ต้องเดาแบบเงียบ ๆ)
4. อัปเดต `app/schemas.py` ให้ validate ค่า status ใหม่
5. อัปเดต `app/routers/crop_cycles.py` ถ้ามีการอ้างอิงชื่อ status เดิม
6. อัปเดต `app/seed.py` ให้ seed ข้อมูลด้วยสถานะใหม่

---

## งานที่ 2: เชื่อม Farm Plots (frontend) กับ CropCycle API จริง

### ปัญหา
`src/pages/FarmPlots.jsx` ใช้ `src/data/mockData.js` แยกต่างหาก ไม่ตรงกับโครงสร้างที่ `GET /crop-cycles` คืนกลับมาจริง

### สิ่งที่ต้องทำ
1. แก้ `src/pages/FarmPlots.jsx` ให้เรียก `GET /crop-cycles` แทน mock data (ใช้ `src/lib/api.js` ที่มีอยู่แล้ว)
2. Map ข้อมูลที่ backend คืนมา (table, batch, crop_type, status, cycle_code) ไปแสดงในตารางที่มีอยู่ ปรับ label สถานะภาษาไทยให้ตรงกับ 5 สถานะใหม่จากงานที่ 1 (ทำ mapping object ระหว่าง enum ↔ ภาษาไทยไว้ที่เดียว เช่น `src/constants/cropCycleStatus.js` เพื่อให้หน้าอื่นเรียกใช้ซ้ำได้)
3. ปุ่มเพิ่ม/แก้ไข/ลบ ต้องเรียก `POST /crop-cycles` และ `PATCH /crop-cycles/{id}` จริง แทนการแก้แค่ React state (ที่หายเมื่อ refresh ตามที่ระบุไว้ใน PROJECT_STATUS.md)
4. Search/filter ที่มีอยู่แล้วในหน้านี้ ให้คงไว้ แต่ทำงานกับข้อมูลจริงที่ดึงมาแทน mock

---

## งานที่ 3: แก้ Plot Detail ให้ใช้ route parameter จริง

### ปัญหา
`src/pages/PlotDetail.jsx` ไม่ได้ใช้ `id` จาก route แสดงแปลงแรกเสมอ

### สิ่งที่ต้องทำ
1. อ่าน `id` จาก route parameter (React Router) แล้วดึงข้อมูล CropCycle ที่ตรงกับ id นั้นจริง (ผ่าน `GET /crop-cycles` แล้ว filter หรือถ้าจะเพิ่ม endpoint `GET /crop-cycles/{id}` ที่ backend เพื่อความเร็ว ก็ทำได้ในรอบนี้เลย)
2. ถ้า id ไม่พบ (เช่น ลบไปแล้ว หรือพิมพ์ url ผิด) ให้แสดงหน้า "ไม่พบข้อมูล" แทนการ fallback ไปแปลงแรกแบบเงียบ ๆ

---

## งานที่ 4: Global 401 / token-expiry handler

### ปัญหา
ตอนนี้ถ้า API ตอบ 401 ระหว่างใช้งาน (token หมดอายุ, JWT_EXPIRE_MINUTES=480) frontend ไม่มีการจัดการ

### สิ่งที่ต้องทำ
1. ใน `src/lib/api.js` เพิ่ม interceptor/wrapper กลางที่เช็ค response status ทุกครั้งที่เรียก API
2. ถ้าเจอ 401 → ลบ token จาก `localStorage` (`organic_farm_token`) แล้ว redirect ไปหน้า Login พร้อมข้อความแจ้งว่า "เซสชันหมดอายุ กรุณาเข้าสู่ระบบใหม่"
3. ต้องทำงานสอดคล้องกับ auth gate ที่มีอยู่แล้วใน `src/App.jsx`

---

## Acceptance criteria (เช็คให้ผ่านก่อนถือว่าจบงาน)

- [ ] Login เป็น owner → เห็น Farm Plots ที่ดึงจาก CropCycle API จริง มี 5 สถานะใหม่ครบ พร้อม `cycle_code` แสดงผล
- [ ] เพิ่ม/แก้ไข/ลบ CropCycle จากหน้า Farm Plots แล้ว refresh หน้าเว็บ → ข้อมูลยังอยู่ (ไม่หาย)
- [ ] เปิด Plot Detail ของโต๊ะที่ 2 กับโต๊ะที่ 5 → ต้องเห็นข้อมูลคนละชุดกันจริง ไม่ใช่ข้อมูลเดิมซ้ำ
- [ ] ลบ/แก้ token ใน localStorage ให้หมดอายุ (หรือรอ 480 นาที) แล้วลองเรียก action ใด ๆ → redirect ไป Login พร้อมข้อความแจ้งเตือน ไม่ error เงียบ ๆ
- [ ] Database เดิมที่มีข้อมูล CropCycle อยู่แล้ว ไม่มีข้อมูลหายหลัง migration status enum
- [ ] ข้อมูล seed (`owner/owner123`, `developer/developer123`) ยังใช้ login ได้ปกติหลังแก้ทั้งหมด

## ขอบเขตที่ห้ามแตะในรอบนี้
- ห้ามเริ่มทำ InputApplication, StockItem, Contract/Order, Transaction, WeatherLog, Task
- ห้ามแก้โครงสร้าง Customer/masking ที่ทำงานถูกต้องอยู่แล้ว
- ห้ามแตะ Inventory, Sales, Costs, Reports, Users, Settings pages
