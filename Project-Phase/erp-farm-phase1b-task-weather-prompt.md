# Prompt: ERP ฟาร์มผักออร์แกนิค — Phase 1 (ต่อ): Task Reminder + WeatherLog

> ก่อนเริ่ม ให้อ่าน `PROJECT_CONTEXT.md` ที่ root ของโปรเจกต์ก่อน โดยเฉพาะส่วน "กับดักที่เคยเกิดขึ้นแล้ว" — งานรอบนี้คือ Task reminder และ WeatherLog เท่านั้น **ห้ามเบี่ยงไปทำ Inventory/Sales/Costs/Reports**

## บริบท
Phase 0 และ Phase 1 (InputApplication) เสร็จแล้ว งานรอบนี้คือ 2 ฟีเจอร์ที่เจ้าของฟาร์มขอโดยตรง: ระบบแจ้งเตือนงาน (เพราะ "บางทีลืม") และระบบพยากรณ์อากาศแบบละเอียด ทำพร้อมกันได้เพราะ Task ต้องใช้ตรรกะเรื่องวันที่ใกล้เคียงกับ Weather และทั้งคู่จะไปอยู่ใน Dashboard ด้วยกัน

---

## ส่วนที่ 1: Task Reminder

### Data model
```
Task
- id
- cycle_id (FK -> CropCycle, nullable — task บางอันไม่ผูกกับรอบปลูกก็ได้)
- title (string)
- due_date (date)
- status ("pending" | "done")
- source ("auto" | "manual")   -- แยกว่า auto-gen จากระบบ หรือเจ้าของฟาร์มพิมพ์เพิ่มเอง
- created_at
```

### Logic การ auto-generate task (สำคัญ)
ทุกครั้งที่สร้างหรือแก้ไข `CropCycle` ให้คำนวณและสร้าง/อัปเดต task ที่เกี่ยวข้องอัตโนมัติ โดยอิงจาก `CropType.nursery_days` และ `CropType.growth_days` ที่มีอยู่แล้ว:

- เมื่อสร้าง CropCycle ใหม่ (status = "อนุบาล") → สร้าง task "ย้ายปลูก [table_number]" ที่ `due_date = nursery_start + nursery_days`
- เมื่อ status เปลี่ยนเป็น "สร้างพุ่ม" → สร้าง task "เตรียมเก็บเกี่ยว [table_number]" ที่ `due_date = transplant_date + growth_days`
- เมื่อ status เปลี่ยนเป็น "เก็บเกี่ยว" → สร้าง task "ทำความสะอาดโต๊ะ [table_number]" ที่ `due_date = วันนี้ + 1`

ถ้า task ที่ควรสร้างมีอยู่แล้วสำหรับ cycle นั้น (ยังไม่ done) ห้ามสร้างซ้ำ ให้อัปเดต `due_date` แทนถ้าวันที่เปลี่ยน

### วันเริ่มเพาะที่แนะนำอัตโนมัติ
ตอนสร้าง CropCycle ใหม่ผ่านฟอร์ม ให้ default ช่องวันที่เป็น **วันอังคารถัดไปจากวันนี้** (ปกติเจ้าของฟาร์มเริ่มเพาะทุกวันอังคาร) แต่แก้เป็นวันอื่นได้อิสระเสมอ ไม่บังคับ

### Backend endpoints
```
GET   /tasks?status=pending&from=&to=    -> list พร้อม filter ช่วงวันที่/สถานะ
POST  /tasks                              -> เพิ่ม task เองแบบ manual
PATCH /tasks/{id}                         -> แก้ไข หรือ mark done
DELETE /tasks/{id}
```

### Frontend
- Dashboard: widget "งานที่ต้องทำ" แสดง task ที่ `due_date <= วันนี้ + 7 วัน` และ `status = pending` เรียงใกล้สุดก่อน, ปุ่มติ๊ก done ได้ในหน้านั้นเลย
- ฟอร์มสร้าง CropCycle: ปรับ default วันที่ตามข้างบน
- หน้า/section แสดง task ทั้งหมด (ไม่ใช่แค่ 7 วัน) เผื่อดูย้อนหลังหรือดูล่วงหน้าไกลกว่านั้น

---

## ส่วนที่ 2: WeatherLog

### Data model
```
WeatherLog
- id
- log_date (date, unique)
- temp_min (float)
- temp_max (float)
- humidity (float, %)
- rainfall (float, mm)
- condition (string, เช่น "ฝนตก", "แดดจัด" — จาก API)
- fetched_at (datetime)
```

### แหล่งข้อมูลพยากรณ์
ใช้ **Open-Meteo API** (https://open-meteo.com) — ฟรี ไม่ต้องขอ API key, มี endpoint ทั้ง current/forecast และ historical พิกัดให้ใช้ของอำเภอดอยสะเก็ด/พื้นที่ฟาร์ม (ถามเจ้าของฟาร์ม lat/long จริงถ้ายังไม่มี ถ้าไม่ได้ระบุใช้พิกัดจังหวัดเชียงใหม่ไปก่อน)

### Logic การเก็บข้อมูล
1. ทำ background job (APScheduler หรือ cron ธรรมดาเรียก endpoint ภายใน) ที่รันวันละครั้ง (เช่น 06:00) → ดึงข้อมูลอากาศของ "เมื่อวาน" (actual, ไม่ใช่ forecast) จาก Open-Meteo → insert เป็น 1 แถวใน `WeatherLog`
2. ถ้าวันนั้นมีข้อมูลอยู่แล้ว (`log_date` ซ้ำ) → update แทน insert (กัน job รันซ้ำ)
3. แยก endpoint สำหรับ **forecast แบบสด** (ไม่เก็บลง DB เพราะเป็นข้อมูลที่เปลี่ยนได้) ไว้โชว์ล่วงหน้า 5-7 วันบน Dashboard

### Backend endpoints
```
GET /weather/forecast          -> เรียก Open-Meteo สด คืน forecast 5-7 วันข้างหน้า
GET /weather/history?from=&to= -> query จาก WeatherLog ที่เก็บสะสมไว้ (ใช้ทำ trend analysis ใน Phase 2 ต่อได้)
```

### Frontend
- Dashboard: widget พยากรณ์อากาศ แสดงอุณหภูมิ/ฝน/ความชื้นของวันนี้ + 5-7 วันข้างหน้าแบบละเอียด (ไม่ใช่แค่ไอคอนเดียว ต้องมีตัวเลขจริงเพราะเจ้าของฟาร์มขอ "ละเอียด")

---

## Acceptance criteria

- [ ] สร้าง CropCycle ใหม่ → เห็น task "ย้ายปลูก" ถูกสร้างอัตโนมัติด้วย due_date ที่คำนวณถูกจาก nursery_days ของ CropType นั้น
- [ ] เปลี่ยน status CropCycle เป็น "สร้างพุ่ม" → task ใหม่ "เตรียมเก็บเกี่ยว" ถูกสร้าง โดยไม่มี task ซ้ำจากขั้นก่อนหน้าที่ done แล้วโผล่มากวนใจ
- [ ] เพิ่ม task เองแบบ manual ได้ และ mark done ได้จาก Dashboard
- [ ] ฟอร์มสร้าง CropCycle ใหม่ default วันที่เป็นวันอังคารถัดไปให้ถูกต้อง แต่แก้ได้
- [ ] Dashboard แสดงพยากรณ์อากาศ 5-7 วันพร้อมตัวเลขอุณหภูมิ/ฝน/ความชื้นจริงจาก Open-Meteo
- [ ] รัน background job ดึงอากาศแล้ว เช็คใน `WeatherLog` เจอแถวใหม่ของเมื่อวาน ไม่มีแถวซ้ำวันเดิม
- [ ] รัน job ซ้ำสองครั้งในวันเดียว → ข้อมูลของวันนั้น update ไม่ insert ซ้ำเป็น 2 แถว
