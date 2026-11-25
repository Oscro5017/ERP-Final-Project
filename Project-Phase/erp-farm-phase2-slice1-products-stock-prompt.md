# Phase 2 / Slice 1: สินค้า + บัญชีความเคลื่อนไหวสต็อก (backend เท่านั้น)

> ใส่ในแชท agent backend (Codex)
> **ก่อนเริ่ม:** อ่าน `docs/AGENT_PRIMER.md` และ `docs/MASKING_POLICY.md` ถ้าไม่พบไฟล์ใดไฟล์หนึ่ง **หยุดและบอกผู้ใช้**
> **branch:** `backend/products-stock` (แตกจาก `main` หลัง merge `backend/key-canary` แล้ว) ถ้าไม่ใช่ branch นี้ **หยุดและบอก**
> แก้ได้เฉพาะ `app/`, `tests/`, `.env.example` (ถ้ามีตัวแปรใหม่) ห้ามแตะ frontend/Flutter/`docs/`/`PROJECT_*.md`/DB จริง/`.env`

## กติกา

ใช้กติกาทั้งหมดใน `docs/AGENT_PRIMER.md` และเพิ่ม:
- **ห้าม commit/push/switch branch เอง** รายงานกลุ่มไฟล์ที่เปลี่ยนต่อแต่ละข้อ
- ถ้าโค้ดจริงขัดกับการตัดสินใจด้านล่าง **หยุดและรายงานก่อนแก้** ห้ามเปลี่ยนการตัดสินใจเอง
- ไม่มี seed สินค้า และไม่ hardcode รายชื่อสินค้าใดๆ
- ใช้ชนิดตัวเลขเดียวกับ `CropCycle.harvest_quantity_kg` / `InputItem.quantity` ที่มีอยู่ (ตรวจจากโค้ด) และปัดทศนิยม 3 ตำแหน่งตอนเขียน

## ขอบเขต

เฉพาะ **Product** และ **StockMovement** (ตาราง, service, endpoint, migration, เทสต์) **ไม่ทำ:** รับเข้า/ส่งออก, ผูก `InputItem`, การเงิน, คู่ค้า, UI, สร้าง movement อัตโนมัติจากแหล่งอื่น (ทำใน slice ถัดไป โดยใช้ service ที่ slice นี้เตรียมไว้)

## การตัดสินใจที่ถือเป็นข้อกำหนด

**Product** (`products`)
- ฟิลด์: `id`, `category` (plaintext; ค่าที่ยอมรับ: `vegetable`, `seed`, `fertilizer`, `chemical`, `blend`, `other` เก็บค่าคงที่ไว้ที่เดียวในโค้ด), `name_encrypted` (**ชื่อสินค้าทุกประเภทเข้ารหัส** เพื่อให้มีเส้นทางโค้ดเดียว; การปิดชื่อผัก/เมล็ดมากกว่าที่นโยบายกำหนดเป็นทางที่ปลอดภัยกว่า และเปลี่ยนภายหลังได้), `name_hash` (HMAC แบบเดียวกับ `InputCatalog`, normalize แบบเดียวกัน), `unit` (หน่วยฐานของสินค้า, plaintext), `reorder_point` (nullable, ≥ 0, plaintext), `is_active` (default true), `created_at`/`updated_at`/`deleted_at`
- ชื่อซ้ำ (normalize แล้วเท่ากัน) ในกลุ่มที่ยังไม่ถูกลบ → 409 พร้อมข้อความทั่วไป **ห้ามส่งชื่อกลับใน error** (ใช้ partial unique index ถ้า SQLite/SQLAlchemy รองรับ ไม่เช่นนั้นตรวจในแอป และรายงานว่าเลือกแบบใด)

**StockMovement** (`stock_movements`)
- ฟิลด์: `id`, `product_id` (FK → products), `quantity_delta` (มีเครื่องหมาย, **หน่วยฐานของสินค้า**, plaintext), `movement_type` (`receipt`, `shipment`, `application`, `adjustment`; ค่าคงที่ที่เดียวในโค้ด), `source_type` + `source_id` (nullable; ไว้ผูกกับต้นทางใน slice ถัดไป), `occurred_at`, `note_encrypted` (nullable), `voided_at` (nullable), `created_at`/`updated_at`
- index: `product_id`, และ (`source_type`, `source_id`)
- **ยอดคงเหลือ = SUM(`quantity_delta`) ของ movement ที่ `voided_at IS NULL`** คำนวณด้วย SQL (ไม่เก็บคอลัมน์สำเนายอด) สำหรับรายการสินค้าให้คำนวณทั้งหมดด้วย query จัดกลุ่มเดียว ไม่ใช่ N+1
- **ยอดติดลบ:** อนุญาตและไม่บล็อก แต่รายการสินค้าต้องบอก `is_negative` ส่วน `is_low` = `on_hand <= reorder_point` เมื่อมี `reorder_point`

**หน่วย**
- 1 สินค้า = 1 หน่วยฐาน ตอนบันทึก movement/ปรับยอด รับหน่วยอื่นในตระกูลเดียวกันแล้วแปลงเป็นหน่วยฐานที่ชั้น service: มวล (`kg`, `g`), ปริมาตร (`l`, `ml`) พร้อมชื่อไทยที่พบบ่อยเป็น alias (กก./กิโลกรัม, กรัม, ลิตร, มล./มิลลิลิตร) แบบ case-insensitive; หน่วยอื่นต้องตรงกับหน่วยฐานของสินค้าเท่านั้น; ข้ามตระกูลหรือไม่รู้จัก → 422 (ข้อความทั่วไป)

**Service (ให้ slice ถัดไปเรียกใช้)** — ห้าม commit เองภายในฟังก์ชัน (ผู้เรียกคุม transaction เพื่อให้แก้ต้นทาง + movement ได้ในครั้งเดียว)
- `record_movement(db, product_id, quantity, unit, movement_type, source_type=None, source_id=None, occurred_at=None, note=None)`
- `void_source_movements(db, source_type, source_id)`
- ฟังก์ชันคำนวณ `on_hand` รายตัวและแบบกลุ่ม

**Endpoint** (ทั้ง owner และ developer อ่าน/เขียนได้ แต่ response ของ developer ถูก mask ตามแบบแผน)
- `GET /products` (`category`, `q` ค้นชื่อด้วยการถอดรหัสในหน่วยความจำ, `include_inactive`, `limit`/`offset` พร้อม `total`); ฟิลด์ที่คืน: `id`, `category`, `name`, `unit`, `reorder_point`, `on_hand`, `is_low`, `is_negative`, `is_active`, `is_masked`, `decrypt_failed`, `created_at`, `updated_at`
- `POST /products`, `PATCH /products/{id}`, `DELETE /products/{id}` (soft delete; movement เดิมคงอยู่; รายการปกติไม่แสดงสินค้าที่ถูกลบ) — การเปลี่ยน `unit` เมื่อมี movement แล้ว ให้ปฏิเสธ (ข้อความทั่วไป)
- `GET /products/{id}/movements` (`limit`/`offset`, ใหม่สุดก่อน; `note` ตามกติกา mask; ฟิลด์ `voided`)
- `POST /products/{id}/adjustments` รับ `counted_quantity` (≥ 0), `unit` (ไม่บังคับ), `note` (ไม่บังคับ), `occurred_at` (ไม่บังคับ) → สร้าง movement ชนิด `adjustment` ที่มี delta = จำนวนที่นับ − ยอดปัจจุบัน (หลังแปลงหน่วย); ถ้า delta = 0 ไม่สร้างแถว และตอบสถานะปัจจุบัน

**Migration**
- ฟังก์ชัน `migrate_products_stock(engine)` (ตามแบบ `migrate_system_meta` ที่มีอยู่): สร้างตารางและ index แบบ additive, idempotent, ไม่แตะตารางเดิม เรียกตอนสตาร์ทตามลำดับที่ถูกต้องเมื่อเทียบกับ canary preflight
- เทสต์ idempotency และ FK ทำงานจริง (movement ที่ไม่มีสินค้าต้องล้มเหลว)

## เทสต์ที่ต้องมี (DB ชั่วคราวเท่านั้น)

CRUD ของสินค้า; owner เห็นชื่อ/note จริง และ developer ได้ ciphertext + `is_masked` (ไม่ถอดรหัส); ชื่อซ้ำ → 409 และไม่รั่วชื่อ; แปลงหน่วย (กก.↔กรัม, ลิตร↔มล., alias ไทย) และปฏิเสธข้ามตระกูล; ยอดคงเหลือหลาย movement, `voided` ไม่ถูกนับ, `is_low`/`is_negative`; ปรับยอดตามนับจริงรวมกรณี delta เป็นศูนย์; `void_source_movements` และ service ไม่ commit เอง (ผู้เรียก rollback แล้วไม่มีแถวเหลือ); แถวสินค้าที่ token เสีย → list ไม่ล่ม มี `decrypt_failed` และ log ไม่รั่วเนื้อหา; ค้นด้วย `q` ข้ามแถวเสีย; ลบแบบ soft delete; migration idempotent; ไม่มี N+1 ใน list (ตรวจจำนวน query หรือโครงสร้าง query); log/response ไม่มีชื่อสินค้าจริงหรือ token

## รายงานท้ายงาน

ตามรูปแบบใน `docs/AGENT_PRIMER.md` และเพิ่ม: (1) ข้อที่การตัดสินใจข้างบนใช้ไม่ได้กับโค้ดจริง (ถ้ามี) พร้อมหลักฐาน (2) รูปแบบ API ที่ slice ถัดไป (รับเข้า/ส่งออก, ผูก `InputItem`) ต้องใช้ต่อ (3) ผลต่อ client เว็บ/Flutter (ยังไม่มีผล เพราะ endpoint ใหม่) (4) ความเสี่ยงที่เหลือ

## Acceptance

- ตาราง `products`/`stock_movements` สร้างได้บน DB ใหม่และ DB เดิมโดยไม่แตะตารางอื่น; รันซ้ำได้
- ยอดคงเหลือถูกต้องด้วย SQL (ไม่ใช้ Python วนทีละสินค้า)
- นโยบาย masking ถูกต้องทั้งสอง role; ไม่มีชื่อสินค้าใน log/error
- เทสต์เดิมทั้งหมดยังอยู่และผ่าน; ไฟล์ที่เปลี่ยนอยู่ในขอบเขต
