# Prompt: ERP ฟาร์มผักออร์แกนิค — Phase 1: InputApplication (บันทึกปุ๋ย/ยา)

## บริบท
Phase 0 เสร็จแล้ว (status enum 5 ค่า, cycle_code, Farm Plots↔CropCycle เชื่อมจริง, global 401 handler) งานรอบนี้คือเพิ่มโมดูลใหม่ตัวแรก: **การบันทึกปุ๋ย/ยาที่ให้กับแต่ละรอบปลูก** ซึ่งเป็นฟีเจอร์ที่เจ้าของฟาร์มขอโดยตรงและยังไม่มีในระบบเลย

**ห้ามแตะ**: Contract/Order, Transaction, StockItem, WeatherLog, Task, Inventory/Sales/Costs/Reports pages เดิม — โฟกัสแค่โมดูลนี้เท่านั้น

## ทำไมต้องออกแบบแบบนี้ (บริบทสำคัญ อย่าข้าม)
- เจ้าของฟาร์มผสมปุ๋ย/ยาหลายชนิดต่อครั้ง ปริมาณไม่คงที่ ปรับตามสภาพแวดล้อม
- **ห้าม hardcode รายชื่อปุ๋ย/ยาไว้ในโค้ดหรือ dropdown ตายตัว** เพราะเจ้าของฟาร์มไม่อยากให้ทีมพัฒนาเห็นสูตร/รายชื่อล่วงหน้า และสูตรก็เปลี่ยนได้ตลอด
- แต่การพิมพ์ชื่อยาว ๆ ซ้ำทุกครั้งก็ไม่สะดวก จึงต้องมี **autocomplete ที่เสนอชื่อจากประวัติที่เคยกรอกเอง** ไม่ใช่ list ที่ตั้งไว้ล่วงหน้า

## Data model ที่ต้องสร้าง

```
InputApplication
- id
- cycle_id (FK -> CropCycle)
- applied_date
- category (string, เช่น "ปุ๋ย" / "ยา" — พิมพ์เองได้เหมือนกัน ไม่บังคับ enum)
- note (text, optional)

InputItem
- id
- application_id (FK -> InputApplication)
- item_name (string, free text)
- quantity (float)
- unit (string, free text)

InputCatalog   (ตารางใหม่ สำหรับ autocomplete — ไม่ใช่ master data ตายตัว)
- id
- item_name (unique)
- last_unit (string, nullable)
- last_category (string, nullable)
- last_used_at (datetime)
- use_count (int, default 0)
```

`InputCatalog` เป็นแค่ cache ของสิ่งที่เจ้าของฟาร์มเคยพิมพ์เอง **ห้าม seed ข้อมูลล่วงหน้าในตารางนี้** ต้องเกิดจากการกรอกจริงเท่านั้น

## Backend endpoints

```
GET  /crop-cycles/{cycle_id}/input-applications     -> list ทั้งหมดของรอบนั้น พร้อม items ที่ผูกอยู่
POST /crop-cycles/{cycle_id}/input-applications      -> สร้างใหม่ พร้อม items หลายรายการในครั้งเดียว (nested payload)
PATCH /input-applications/{id}                        -> แก้ไข (เผื่อพิมพ์ผิด)
DELETE /input-applications/{id}                       -> ลบ

GET  /input-catalog/suggestions?q=<คำที่พิมพ์>&limit=10
     -> คืนรายการ item_name ที่ตรงกับ q (LIKE '%q%') เรียงตาม last_used_at DESC
     -> response แต่ละรายการรวม last_unit, last_category ไปด้วย เพื่อให้ frontend auto-fill ได้
```

### Logic สำคัญตอนบันทึก InputItem ใหม่
ทุกครั้งที่มีการสร้าง `InputItem` ใหม่ (ไม่ว่าจะเลือกจาก suggestion หรือพิมพ์ชื่อใหม่เอง):
1. Upsert ลง `InputCatalog`: ถ้า `item_name` มีอยู่แล้ว (match แบบ exact, case-insensitive) → update `last_unit`, `last_category`, `last_used_at = now()`, `use_count += 1`
2. ถ้ายังไม่มี → insert แถวใหม่ด้วย `use_count = 1`
3. ทำ logic นี้เป็น service function แยก (เช่น `app/services/input_catalog.py`) เพื่อให้เรียกซ้ำจากที่อื่นได้ในอนาคตถ้าจำเป็น

## Frontend (HTML/React admin panel)

### หน้าที่ต้องมี
เพิ่ม section "บันทึกปุ๋ย/ยา" ใน Plot Detail (`src/pages/PlotDetail.jsx`) ของแต่ละ CropCycle:

1. **ฟอร์มเพิ่มการให้ปุ๋ย/ยาใหม่**
   - เลือกวันที่ (default = วันนี้)
   - ช่อง category — ใช้ input + datalist เหมือนกัน (ไม่บังคับค่า)
   - รายการ item ที่เพิ่มได้หลายแถว (dynamic list, ปุ่ม "+ เพิ่มรายการผสม")
   - แต่ละแถว: ช่อง item_name เป็น **input + datalist** ผูกกับ `GET /input-catalog/suggestions` (debounce การเรียก API ~300ms ตอนพิมพ์), ช่อง quantity (number), ช่อง unit (input + datalist เช่นกัน — ใช้ `last_unit` จาก suggestion ที่เลือกมา auto-fill ให้ ถ้าผู้ใช้ยังไม่ได้แก้เอง)
   - ปุ่มบันทึก → เรียก `POST /crop-cycles/{cycle_id}/input-applications`

2. **ตารางประวัติการให้ปุ๋ย/ยาของรอบนั้น**
   - แสดงย้อนหลังทั้งหมด เรียงวันที่ล่าสุดก่อน
   - แต่ละแถวขยายดูรายการ item ที่ผสมได้ (accordion หรือ expand row)
   - ปุ่มแก้ไข/ลบ

### Component ที่ควรแยกใช้ซ้ำ
สร้าง component กลาง เช่น `<AutocompleteInput suggestionsUrl="/input-catalog/suggestions" onSelect={...} />` เพื่อใช้ซ้ำได้ทั้งกับช่อง item_name, category, และ unit โดยไม่ต้องเขียนโค้ด fetch/debounce ซ้ำ 3 รอบ

## Acceptance criteria

- [ ] พิมพ์ชื่อปุ๋ยใหม่ที่ไม่เคยมีมาก่อน → บันทึกได้ปกติ ไม่มีข้อความ error ใด ๆ บังคับให้เลือกจาก list
- [ ] พิมพ์ชื่อปุ๋ยที่เคยกรอกมาก่อน (พิมพ์บางส่วน เช่น "ปุ๋ย A") → เห็น suggestion โผล่ขึ้นมาให้เลือก
- [ ] เลือก suggestion แล้ว → ช่อง unit auto-fill จากค่าล่าสุดที่เคยใช้กับชื่อนั้น แต่ยังแก้เองได้
- [ ] เพิ่ม InputApplication ที่มีหลาย item ผสมกันในครั้งเดียว → บันทึกครบทุก item ที่ผูกกับ application เดียวกัน
- [ ] Reload หน้าเว็บ → ประวัติที่บันทึกไว้ยังอยู่ครบ ไม่หาย
- [ ] Login เป็น developer role → ยังเห็นและกรอก InputApplication ได้ปกติ (ข้อมูลนี้ไม่ได้อยู่ในหมวดที่ต้อง mask ตาม requirement เดิม — mask เฉพาะ Customer name/contact/revenue เท่านั้น)
- [ ] ตาราง `InputCatalog` ไม่มีข้อมูล seed ล่วงหน้า มีแต่สิ่งที่เกิดจากการกรอกจริงระหว่างทดสอบ
