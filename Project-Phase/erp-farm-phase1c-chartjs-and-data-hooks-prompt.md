# Prompt: ERP ฟาร์มผักออร์แกนิค — Phase 1c: ย้ายกราฟไป Chart.js + ช่องรอเก็บข้อมูลสำหรับ AI

> ก่อนเริ่ม ให้อ่าน `PROJECT_CONTEXT.md` ที่ root ของโปรเจกต์ โดยเฉพาะหัวข้อ "ช่องรอ AI", "การตัดสินใจด้านเทคโนโลยีที่ล็อกแล้ว" และ "กับดักที่เคยเกิดขึ้นแล้ว" แล้วบันทึกไฟล์นี้ไว้ที่ `docs/phases/phase-1c-chartjs-and-data-hooks.md`
>
> งานนี้ทำต่อจาก Phase 1b (Task reminder + WeatherLog) เป็นงานเล็ก **ห้ามเริ่มทำ Contract/Order, Transaction, StockItem, LaborLog, Insight หรือส่วน AI ใด ๆ ในรอบนี้**

## บริบท
1. เอกสารของโปรเจคระบุว่าใช้ **Chart.js** แต่โค้ดจริงใช้ Recharts อยู่ → ต้องปรับโค้ดให้ตรงตามเอกสาร
2. ส่วน AI จะทำหลัง Phase 4 แต่ข้อมูลที่โมเดลจะใช้ต้องเริ่มเก็บตั้งแต่ตอนนี้ ไม่งั้นข้อมูลช่วงนั้นหายถาวร จึงเพิ่มฟิลด์/ตารางเก็บข้อมูลเล็ก ๆ ไว้ล่วงหน้า (ยังไม่มีการวิเคราะห์หรือโมเดลใด ๆ)

---

## งานที่ 1: ย้าย Recharts → Chart.js

### สิ่งที่ต้องทำ
1. ติดตั้ง `chart.js` และ `react-chartjs-2` (`npm install chart.js react-chartjs-2`)
2. ค้นหาทุกที่ที่ import จาก `recharts` (เริ่มจาก Dashboard, Reports และหน้าอื่น ๆ ที่ใช้กราฟ) แล้วทำรายการให้ครบก่อนแก้
3. สร้าง wrapper component กลางที่ `src/components/charts/` เช่น `LineChart.jsx`, `BarChart.jsx`, `DoughnutChart.jsx` (เท่าที่มีกราฟชนิดนั้นอยู่จริง ไม่ต้องสร้างชนิดที่ไม่ได้ใช้) เพื่อให้กราฟใหม่ในอนาคต (พยากรณ์อากาศ, รายได้ต่อลูกค้า, แนวโน้มราคา) เรียกใช้ซ้ำได้
4. **ลงทะเบียนเฉพาะส่วนของ Chart.js ที่ใช้จริง** (`Chart.register(...)` เฉพาะ scale/element/plugin ที่จำเป็น) เพื่อไม่ให้ bundle ใหญ่เกินจำเป็น
5. แก้หน้าที่ใช้กราฟทีละหน้าให้เรียก wrapper ใหม่ โดยให้หน้าตาและข้อมูลที่แสดงเหมือนเดิม (ไม่ต้องออกแบบใหม่)
6. กราฟต้องรองรับภาษาไทยในแกน/tooltip/legend และ responsive ตามเดิม
7. เมื่อไม่มีการ import `recharts` เหลือแล้ว ให้ถอนออกจาก `package.json` (`npm uninstall recharts`)
8. ถ้าหน้า WeatherLog/พยากรณ์อากาศจาก Phase 1b มีกราฟอยู่แล้ว ให้ใช้ Chart.js ด้วยเช่นกัน

### ข้อควรระวัง
- ย้ายเฉพาะไลบรารีกราฟ ห้ามเปลี่ยน logic ดึงข้อมูลหรือโครงสร้างหน้าอื่น
- ถ้าเจอกราฟที่ Chart.js ทำให้เหมือนเดิมไม่ได้ทั้งหมด ให้ทำใกล้เคียงที่สุดแล้วบันทึกความต่างไว้ใน `PROJECT_STATUS.md` ไม่ต้องฝืน

---

## งานที่ 2: ช่องรอ AI ชุดที่ 1 (เก็บข้อมูล)

### 2.1 ปริมาณผลผลิตต่อรอบ
เพิ่มใน `CropCycle`:
```
harvest_quantity_kg (float, nullable)   -- น้ำหนักที่เก็บได้จริงของรอบนั้น
```
- แสดงเป็นช่องกรอกในฟอร์มแก้ไข CropCycle และใน Plot Detail เมื่อสถานะเป็น "เก็บเกี่ยว" (ไม่บังคับกรอก)
- รวมใน schema/response ของ `GET /crop-cycles` และ `PATCH /crop-cycles/{id}`

### 2.2 ประวัติการเปลี่ยนสถานะ
ตารางใหม่:
```
CropCycleStatusLog
- id
- cycle_id (FK -> CropCycle)
- from_status (nullable ตอนสร้างรอบใหม่)
- to_status
- changed_at (datetime)
```
- สร้างแถวใหม่อัตโนมัติทุกครั้งที่สร้าง CropCycle (from_status = null) และทุกครั้งที่ status เปลี่ยน (ทำใน service/router ที่เดียว อย่ากระจายตามหลายที่)
- ถ้า Phase 1b สร้าง Task อัตโนมัติจากการเปลี่ยนสถานะอยู่แล้ว ให้เขียน log จาก logic จุดเดียวกัน
- migration: สร้างแถว log เริ่มต้นให้ CropCycle เดิมที่มีอยู่ (to_status = สถานะปัจจุบัน, from_status = null, changed_at = created_at ถ้ามี ไม่งั้นใช้เวลา migrate) ห้ามลบหรือแก้ข้อมูลเดิม
- เพิ่ม `GET /crop-cycles/{id}/status-log` คืน log เรียงตามเวลา และแสดงเป็น timeline เล็ก ๆ ใน Plot Detail

### 2.3 Timestamps และ soft delete
- เพิ่ม `created_at`, `updated_at` ในตารางหลักที่ยังไม่มี: CropCycle, Customer, InputApplication, InputItem, Task, WeatherLog (ตรวจของที่มีอยู่ก่อน อย่าเพิ่มซ้ำ)
- เพิ่ม `deleted_at` (nullable) ใน CropCycle, Customer, InputApplication, Task และเปลี่ยน DELETE endpoint ของตารางเหล่านี้เป็น soft delete (ตั้ง `deleted_at`) แทนการลบจริง
- ทุก query ที่ list ข้อมูลต้องกรอง `deleted_at IS NULL` เป็นค่าเริ่มต้น (ทำเป็น helper/mixin กลาง อย่าเขียน filter ซ้ำทุก endpoint)
- migration ต้องเติม `created_at` ให้แถวเดิมด้วยเวลา migrate (หรือวันที่ที่มีอยู่แล้วในตาราง) โดยไม่ทำข้อมูลเดิมหาย

---

## Acceptance criteria

- [ ] `grep -r "recharts" src/` ไม่เจออะไรเหลือ และ `package.json` ไม่มี `recharts`
- [ ] ทุกหน้าที่เคยมีกราฟยังแสดงกราฟได้เหมือนเดิม ข้อความไทยแสดงถูกต้อง
- [ ] มี wrapper component กลางใน `src/components/charts/` และกราฟทุกตัวเรียกผ่าน wrapper
- [ ] `npm run build` ผ่าน
- [ ] กรอกน้ำหนักผลผลิตในรอบที่เก็บเกี่ยวแล้ว บันทึกได้และ refresh แล้วยังอยู่
- [ ] เปลี่ยนสถานะ CropCycle 1 ครั้ง → เห็นแถวใหม่ใน status log พร้อมเวลา และ timeline ใน Plot Detail แสดงถูก
- [ ] CropCycle เดิมที่มีก่อน migration มี log เริ่มต้นหนึ่งแถว ไม่มีข้อมูลเดิมหาย
- [ ] ลบ CropCycle/Customer/InputApplication/Task แล้วไม่หายจาก DB (มี `deleted_at`) แต่ไม่โผล่ในหน้า list
- [ ] Login เป็น developer → ยังเห็น/ใช้งานเรื่องเหล่านี้ได้ตามปกติ และ masking ของ Customer ยังทำงานเหมือนเดิม
- [ ] เพิ่ม/อัปเดต tests สำหรับ status log และ soft delete อย่างน้อยอย่างละ 1 ชุด

## ขอบเขตที่ห้ามแตะในรอบนี้
- ห้ามสร้างตาราง `Insight`, endpoint `/insights`, หรือโค้ดวิเคราะห์/ML ใด ๆ (เป็นงานของ Phase 2 และ Phase 5)
- ห้ามแก้โครงสร้าง encryption/masking ของ Customer
- ห้ามเริ่มโมดูลของ Phase 2 เป็นต้นไป
- หลังทำเสร็จ ให้อัปเดตสถานะในตาราง index ของ `PROJECT_CONTEXT.md` และ `PROJECT_STATUS.md`
