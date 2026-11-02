# Front-end Blueprint: Developer Desktop

วันที่วิเคราะห์: 31 ตุลาคม 2026  
SCOPE: `developer-desktop`  
สถานะ: วิเคราะห์และออกแบบเท่านั้น ยังไม่มีการแก้โค้ดหรือฐานข้อมูล

## สรุปผู้บริหาร

- **จำนวน frontend:** production เป็น React/Vite app เดียว แบ่งมุมมองตาม role ที่ API; ไม่พบโค้ด `code_prototype` ใน root workspace จึงตรวจจำนวน entry point ของต้นแบบแยกไม่ได้ (เอกสารบอกว่าเป็น baseline) หลักฐาน: [src/main.jsx](src/main.jsx), [src/App.jsx](src/App.jsx), [PROJECT_STATUS.md](PROJECT_STATUS.md#L1).
- **ปัญหาหลัก:** เมนู 10 รายการสะท้อน template มากกว่างานจริง, Dashboard/Inventory/Sales/Harvest/Costs ใช้ mock, การเงินและสต็อกยังไม่มี backend, mobile sidebar ยังยุบแต่ไม่ทำเป็น drawer, และ CustomerPanel มี confirm dialog ที่ส่งค่า `name` เต็มเข้า `window.confirm` แม้เป็น ciphertext.
- **ภาพเป้าหมาย:** `ภาพรวม | ฟาร์ม | สภาพอากาศ | สินค้า & คลัง | รับเข้า / ส่งออก | การเงิน` เป็นเมนูหลัก; `คู่ค้า`, `ตั้งค่า` เป็นเมนูรอง; เพิ่ม `สถานะระบบ` สำหรับ developer โดยเฉพาะ.
- **5 เรื่องที่ต้องตัดสินใจก่อน Phase 2:** (1) สินค้า/StockMovement เป็นแหล่ง stock เดียว และ InputCatalog จะยุติอย่างไร (2) หน่วยมาตรฐาน/การแปลง (3) ตัวเลขต้นทุนและค่าแรงทั้งหมดเป็นความลับจาก developer หรือไม่ (4) ค่าแรงใช้จำนวนคน×ชั่วโมงหรือระบุ worker รายคน (5) จะรวม `Recommendation` กับ `Insight` เป็น resource เดียวชื่อใด.
- **ลำดับที่แนะนำ:** ทำ route/nav และความปลอดภัยของข้อมูลเดิมก่อน; ต่อด้วย Farm, Weather, Overview, Customer API; ทำหน้า backend ที่ยังไม่มีเป็น shell ที่ไม่มีตัวเลขปลอม; ตัดสินโมเดล stock ก่อน backend Phase 2.

## 1. As-Is: แผนที่ Frontend ปัจจุบัน

### 1.1 จำนวนแอปและ entry point

| รายการ | สิ่งที่ตรวจพบ | หลักฐาน |
|---|---|---|
| Production frontend | 1 React/Vite app; `src/main.jsx` สร้าง root, `BrowserRouter` และ render `App` | [src/main.jsx](src/main.jsx), [package.json](package.json) |
| Authentication | Login เป็น auth gate ใน `App`; เมื่อมี token แสดง route ภายใน `DashboardLayout` | [src/App.jsx](src/App.jsx), [src/lib/api.js](src/lib/api.js) |
| Role | `getRole()` อ่าน role จาก JWT ฝั่ง client; การ mask จริงต้องเชื่อ response boundary ของ backend ไม่ใช่การซ่อน route ใน React | [src/lib/api.js](src/lib/api.js), `get_current_role` ใน `app/routers/customers.py` |
| `code_prototype` | ไม่พบใน root workspace ที่ตรวจ; `PROJECT_STATUS.md` ระบุว่าเป็น UI baseline แยก แต่ตรวจ source/entry point จริงไม่ได้ | [PROJECT_STATUS.md](PROJECT_STATUS.md#L1), รายการ root workspace |
| URL ที่ไม่รู้จัก | `App.jsx` ไม่มี `*`/404 route; URL ที่ไม่ match มีโอกาสเห็น layout ว่าง | [src/App.jsx](src/App.jsx) |

### 1.2 Routes ทั้งหมด

สถานะใช้ตามความจริงของ API ปัจจุบัน: `มี API จริง`, `ผสม`, `mock ทั้งหมด`. `Login` เป็น auth gate ไม่ใช่ route ที่ประกาศแยก. Route declaration อยู่ใน [src/App.jsx](src/App.jsx#L33-L45); เมนูเดิมอยู่ใน [src/data/mockData.js](src/data/mockData.js#L1-L11).

| Path ปัจจุบัน | Component / หลักฐาน | API ที่เรียก | สถานะ | เมนูเดิมและข้อเสนอปลายทาง |
|---|---|---|---|---|
| `/` | `Dashboard` — [src/pages/Dashboard.jsx](src/pages/Dashboard.jsx) | `/weather/forecast`, `/weather/sync-yesterday`, `/tasks`, `/customers`; สถิติ/กราฟ/เก็บเกี่ยว/stock เป็นข้อมูลใน `mockData` | ผสม | หน้าภาพรวม → `/` |
| `/plots` | `FarmPlots` — [src/pages/FarmPlots.jsx](src/pages/FarmPlots.jsx) | `/crop-cycles`, `/tables`, `/batches`, `/crop-types`; CRUD `/crop-cycles/{id}` | มี API จริง | แปลงเพาะปลูก → `/farm/cycles` |
| `/plots/:id` | `PlotDetail` — [src/pages/PlotDetail.jsx](src/pages/PlotDetail.jsx) | `/crop-cycles`, `/{cycle_id}/status-log`, `/input-applications`, `/input-catalog/suggestions` | มี API จริง | ไม่มี Sidebar link; จากปุ่มดูรายละเอียด → `/farm/cycles/:id` |
| `/activities` | `Activities` — [src/pages/Activities.jsx](src/pages/Activities.jsx) | `/tasks`, `/crop-cycles`; CRUD และ filter/search | มี API จริง | กิจกรรมการเพาะปลูก → `/farm/activities` |
| `/harvest` | `Harvest` — [src/pages/Harvest.jsx](src/pages/Harvest.jsx) | ไม่มี; ใช้ `harvestData` | mock ทั้งหมด | ผลผลิต → `/farm/cycles?status=harvested` (ไม่คงหน้าซ้ำ) |
| `/inventory` | `Inventory` — [src/pages/Inventory.jsx](src/pages/Inventory.jsx) | ไม่มี; ใช้ `inventoryData` | mock ทั้งหมด | คลังสินค้า → `/products` |
| `/sales` | `Sales` — [src/pages/Sales.jsx](src/pages/Sales.jsx) | ไม่มี; ใช้ `salesData` | mock ทั้งหมด | การขาย → `/trade/outbound` |
| `/costs` | `Costs` — [src/pages/Costs.jsx](src/pages/Costs.jsx) | ไม่มี; ใช้ `costData` | mock ทั้งหมด | ต้นทุนและกำไร → `/finance` |
| `/reports` | `Reports` — [src/pages/Reports.jsx](src/pages/Reports.jsx) | ไม่มี | mock ทั้งหมด/placeholder | รายงาน → `/finance/reports` |
| `/users` | `Users` — [src/pages/Users.jsx](src/pages/Users.jsx) | ไม่มี; ใช้ `userData` | mock ทั้งหมด | ผู้ใช้งาน → `/settings/users` (ซ่อน/ปิดจนมี API) |
| `/settings` | `Settings` — [src/pages/Settings.jsx](src/pages/Settings.jsx) | ไม่มี | placeholder | ตั้งค่า → `/settings/profile` (owner เท่านั้น) |

API truth: router registration อยู่ที่ [app/main.py](app/main.py#L104-L111); endpoint จริงอยู่ใน [app/routers/crop_cycles.py](app/routers/crop_cycles.py), [app/routers/reference.py](app/routers/reference.py), [app/routers/tasks.py](app/routers/tasks.py), [app/routers/weather.py](app/routers/weather.py), [app/routers/customers.py](app/routers/customers.py), [app/routers/input_applications.py](app/routers/input_applications.py), [app/routers/sensors.py](app/routers/sensors.py). ไม่มี router สำหรับ product/stock, supplier, sales/order, transaction/finance, user management, health/jobs/backup หรือ ForecastSnapshot read API.

### 1.3 Shared components

| Component | ใช้ที่ไหน / สถานะ | นำกลับมาใช้ได้ | ข้อสังเกต |
|---|---|---|---|
| `DashboardLayout` | ครอบทุก route หลัง login | สูง: ใช้ต่อได้หลังเปลี่ยน navigation | margin ซ้าย fix ตาม sidebar; ไม่มี mobile drawer จริง (`src/layouts/DashboardLayout.jsx`) |
| `Sidebar` + `Navbar` | ทุกหน้าหลัง login | โครงใช้งานต่อได้ | รายการเมนูมาจาก mockData; search/bell/profile บางส่วนไม่มี workflow/API; profile label เป็นค่าคงที่ (`src/components/Sidebar.jsx`, `Navbar.jsx`) |
| `DataTable` | FarmPlots | กลาง | ใช้ต่อกับ desktop table; ไม่มี loading/empty state, sort เป็น icon อย่างเดียว, mobile เลื่อนแนวนอน (`src/components/DataTable.jsx`) |
| `Modal` | FarmPlots, PlotDetail | กลาง | dialog พื้นฐาน ไม่มี focus management/escape handling ระบุไว้ใน component; mobile form ควรเป็นหน้า/แผ่นเต็ม (`src/components/Modal.jsx`) |
| `Toast` | Dashboard, FarmPlots | สูงเมื่อปรับ a11y | แสดงข้อความที่ส่งเข้าโดยตรง จึงต้องไม่ใส่ ciphertext/private error ลงไป (`src/components/Toast.jsx`) |
| `AutocompleteInput` | PlotDetail | ต่ำถึงกลาง | เหมาะกับ InputCatalog เดิมชั่วคราว; D4 ต้องเปลี่ยนจาก free text เป็นเลือก product id และแสดง stock (`src/components/AutocompleteInput.jsx`) |
| `TaskWidget` | Dashboard | สูง | API จริง, รองรับ manual title masked; ปุ่ม mark-done 24px และปุ่มบางตัวซ่อนจน hover (`src/components/TaskWidget.jsx`) |
| `WeatherWidget` | Dashboard | สูง | `/weather/forecast` จริง มี loading/error/retry; ปัจจุบันอยู่ใน dashboard ไม่ใช่หน้า weather แยก (`src/components/WeatherWidget.jsx`) |
| `CustomerPanel` | Dashboard | ปานกลาง | Customer API จริงและย่อ token; ย้ายไป Partners. `handleDelete` ใช้ `customer.name` ตรงใน confirm จึงเสี่ยงเปิด ciphertext เต็มต่อ developer (`src/components/CustomerPanel.jsx`, `CustomerPanel.handleDelete`) |
| `StatCard`, `LowStockCard` | Dashboard | กลาง | นำเสนอข้อมูลได้ แต่ค่าปัจจุบันเป็น mock; เปลี่ยนเป็น API-backed widgets เท่านั้น (`src/components/StatCard.jsx`, `LowStockCard.jsx`) |
| `PlotChart`, `RevenueChart`, chart wrappers | Dashboard | wrapper ใช้ซ้ำได้ | ใช้ Chart.js ผ่าน `src/components/charts/`; input ปัจจุบันเป็น mock; developer ห้ามเห็นกราฟรายได้จากตัวเลขจริง (`PlotChart`, `RevenueChart`, `LineChart`, `DoughnutChart`) |
| `StatusBadge`, `dateUtils` | Farm/Tasks | สูง | ใช้ต่อกับ status mapping และภาษาไทยได้ (`src/components/StatusBadge.jsx`, `src/utils/dateUtils.js`) |

โค้ดซ้ำที่เห็น: การจัดกรอบ panel/table และการแสดง empty/loading เขียนแยก; กลไกแสดง masked text กระจายตาม `CustomerPanel`, `TaskWidget`, `Activities`, `PlotDetail`. ควรทำ shared security presentation ไม่ใช่รวมทุกหน้าด้วย abstraction ใหญ่.

### 1.4 Responsive และมือถือ

| ประเด็น | สถานะที่ตรวจพบ | หลักฐาน |
|---|---|---|
| Viewport | มี `<meta name="viewport" content="width=device-width, initial-scale=1.0">` | [index.html](index.html) |
| Breakpoints | ใช้ Tailwind `sm`, `md`, `lg`, `xl` เป็นบางส่วน ไม่ใช่ mobile-first ครบทุกหน้าที่ข้อมูลหนาแน่น | `Dashboard`, `FarmPlots`, `PlotDetail`, `WeatherWidget` |
| Sidebar | `fixed` อยู่ซ้ายตลอด; ปุ่มมือถือสลับ collapsed width ไม่ได้ซ่อนเป็น overlay; `DashboardLayout` ยังให้ `ml-72`/`ml-20` บนทุก viewport จึงกินพื้นที่จอแคบ | [src/components/Sidebar.jsx](src/components/Sidebar.jsx), [src/layouts/DashboardLayout.jsx](src/layouts/DashboardLayout.jsx), [src/components/Navbar.jsx](src/components/Navbar.jsx) |
| ตาราง | CustomerPanel, DataTable, Harvest, Inventory, Sales และ PlotDetail history มี `overflow-x-auto`; จอแคบต้องเลื่อนแนวนอน | `DataTable`, `CustomerPanel`, `Harvest`, `Inventory`, `Sales`, `PlotDetail` |
| Form | FarmPlots/PlotDetail ใช้ grid ที่ลด column ได้บางตำแหน่ง; PlotDetail edit item form มี `grid-cols-[...]` คงที่บนมือถือ | `PlotDetail.renderItemRow` และ Edit Modal |
| พื้นที่แตะ | ไม่มีมาตรฐาน min 44px; TaskWidget มี control 24px, icon controls หลายจุดเป็น padding 8px; ปุ่มบางส่วนพึ่ง hover | `TaskWidget`, `DataTable`, `Navbar`, `PlotDetail` |
| PWA | ไม่มี manifest/service worker ใน entry ที่ตรวจ; responsive + manifest ขั้นต่ำเหมาะกับการทดลองก่อน Flutter หากไม่ต้อง offline แต่ยังต้องทดสอบติดตั้งบน iOS/Android, safe-area, push notification และ camera/native integration | [index.html](index.html), root file listing |

### 1.5 Role และ masking

| หน้า/ข้อมูล | Owner | Developer | ช่องว่าง/หลักฐาน |
|---|---|---|---|
| Customer | API ส่ง plaintext; UI แสดง | API ส่ง token + `is_masked`; UI ย่อและ copy ได้ | `CustomerPanel.handleDelete` ใช้ `window.confirm` กับ `customer.name` เต็ม; แก้เป็นข้อความคงที่หรือ label ปลอดภัยก่อนเปิด developer view. [app/routers/customers.py](app/routers/customers.py), `CustomerPanel` |
| Manual Task | title จริง | API ส่ง ciphertext + `is_masked`; UI แสดง “ข้อมูลเข้ารหัส” | Activities ซ่อน edit เมื่อ masked และ search เฉพาะ owner; TaskWidget แสดง label ย่อ. [app/routers/tasks.py](app/routers/tasks.py), `Activities`, `TaskWidget` |
| Input application | owner เห็น item/quantity/note จริง | Developer: item name/note เป็น `ข้อมูลเข้ารหัส`; quantity ต้องเป็นตัวเลขจริงตาม policy; ปัจจุบัน API/DB ยังเข้ารหัส quantity จึงต้องรอ D4 migration/API contract ก่อนเปิดใน UI; unit/category/date เปิด | `PlotDetail` ปัจจุบันยัง mask quantity; autocomplete developer ไม่มี suggestion. [app/routers/input_applications.py](app/routers/input_applications.py), `PlotDetail`, `AutocompleteInput`, MASKING_POLICY.md |
| ตัวเลขการเงิน | ไม่มีข้อมูลเงินจริงใน API ปัจจุบัน | ยังไม่มี view/API; ห้ามใช้ demo numbers เสมือนจริง | helper `present_aggregate` มีไว้เตรียมใช้; transaction ยังไม่เริ่ม. `app/services/secure_fields.py`, `PROJECT_CONTEXT.md` Phase 2 |
| Route access | App แสดงทุก route หลัง login | ไม่มี role-based route guard ใน React; ต้องถือว่า API เป็น security boundary | `src/App.jsx`, `src/lib/api.js` |
| Toast/error/dialog | ขึ้นกับข้อความที่ส่งเข้า component | ต้องไม่แสดง raw ciphertext, secret, หรือข้อมูล request | `Toast`, `api()` ส่ง detail error เข้า component; Customer confirm เป็นจุดยืนยันที่รั่ว |

**กฎ UI สำหรับ developer:** แสดง label `ข้อมูลเข้ารหัส` เป็นค่าเริ่มต้น; ถ้าจำเป็นต้องตรวจ ciphertext ให้มีการเปิดดูแบบ explicit, จำกัดความกว้าง, ไม่วางใน dialog/toast/error, copy ผ่าน action แยก และอย่าบันทึกลง console. `is_masked` ต้องเป็นตัวกำหนด presentation; ห้ามเดาจาก prefix token.

### 1.6 Loading / empty / error

| หน้า | Loading | Empty | Error | สถานะ |
|---|---|---|---|---|
| Dashboard | Weather/Task แยกกัน | Widget task/weather มีบางกรณี | Weather แสดง error/retry; Dashboard ไม่มี global error state | ผสม mock/API |
| FarmPlots | ไม่มี state แสดง loading | DataTable ว่างแต่ไม่มีข้อความ | Toast จาก `loadData` | API จริง; ต้องเพิ่มสถานะชัด |
| PlotDetail | มี loading/error/not-found | มีข้อความเมื่อไม่มีประวัติ | inline error; delete ใช้ alert | API จริง; ปรับ safe errors |
| Activities | loading/empty/message | มี “ไม่พบงาน” | แสดง message | API จริง; ดีที่สุดในหน้าปัจจุบัน |
| Weather (ยังไม่มี route) | WeatherWidget loading | ไม่มี empty แบบ data history | error/retry | ใช้ widget ปัจจุบันเป็นฐาน |
| CustomerPanel | loading/empty/message | มี empty state | message | API จริง; เพิ่ม retry และ safe confirm |
| Harvest/Inventory/Sales/Costs/Users/Reports/Settings | ไม่มี | ไม่มี empty state ตาม domain | ไม่มี | แสดง mock/ข้อความคงที่โดยไม่บอกสถานะข้อมูล |

หลักฐาน: `FarmPlots.loadData`, `PlotDetail` loading branches, `Activities` state branches, `WeatherWidget`, `CustomerPanel`, mock page components.

### 1.7 Bundle และ code splitting

อ่าน build output ที่มีอยู่ใน `frontend/assets` โดยไม่ build ทับ: JS `533,337 bytes`, CSS `38,422 bytes`, รวม `571,759 bytes` (ประมาณ `571.8 kB` แบบฐานสิบ, `558.4 KiB`; ไม่รวม gzip). Vite มี warning เดิมใน `PROJECT_STATUS.md` ว่า chunk ใหญ่กว่า 500 kB. ไฟล์: [frontend/assets/index-D2eVbOmp.js](frontend/assets/index-D2eVbOmp.js), [frontend/assets/index-D6sw-Zmp.css](frontend/assets/index-D6sw-Zmp.css). ไม่มีการวัด gzip หรือเปรียบเทียบ build ใหม่.

ข้อเสนอ: `React.lazy`/`Suspense` แยก route chunks สำหรับ Chart.js, developer status และหน้าที่ไม่เปิดบ่อย; shared component ที่ใช้ในทุกหน้าให้อยู่ใน initial chunk. ตั้งเป้าตรวจขนาดหลัง build ไปยัง temp directory ตามข้อกำหนด ห้ามเขียนทับ `frontend/`.

### 1.8 หลักฐานที่ทำให้เมนู/หน้ารก

- Sidebar มี 10 entries แต่ `/plots/:id` ไม่อยู่ในเมนู; route ประกาศ 11 หน้า (ไม่นับ Login gate). [src/data/mockData.js](src/data/mockData.js#L1-L11), [src/App.jsx](src/App.jsx#L33-L45).
- Dashboard มีทั้งสถิติ, chart, ผลผลิต, low-stock, weather, task และลูกค้า; หลายส่วนเป็น mock, ซ้ำกับเมนูแยก และมีตัวเลขการเงินที่ frontend ไม่ควรใช้เป็นข้อมูลจริง. [src/pages/Dashboard.jsx](src/pages/Dashboard.jsx), [src/data/mockData.js](src/data/mockData.js).
- Inventory/Sales/Harvest/Costs/Users ใช้ mock arrays; ปุ่มเพิ่ม/สร้างใน Inventory/Sales ไม่ผูก action; Reports/Settings เป็นข้อความ placeholder. อ้างอิง component ชื่อเดียวกับหน้าใน `src/pages/`.
- Navbar มี search, bell และ profile UI แต่ไม่พบ search handler, notification API หรือ profile API; Sidebar profile เป็นค่าคงที่. [src/components/Navbar.jsx](src/components/Navbar.jsx), [src/components/Sidebar.jsx](src/components/Sidebar.jsx).
- สินค้า/คลัง, รับเข้า/ส่งออก และการเงินยังไม่มี backend; ต้องไม่เปิดหน้าที่ทำให้ผู้พัฒนา/เจ้าของเข้าใจว่า mock เป็น record จริง.

## 2. To-Be: หน้าสำหรับ Developer Desktop

### กติกากลางของหน้าฝั่ง developer

- Desktop-first: sidebar แคบและคงที่, content กว้างพอสำหรับตรวจข้อมูล, ตารางย่อ/ขยายได้, มี breadcrumb และ role badge `DEVELOPER` ชัดเจน.
- หน้าธุรกิจที่ใช้ข้อมูลจริงแสดงข้อมูลที่ API อนุญาต; developer เห็น `ข้อมูลเข้ารหัส` แทนชื่อ/ข้อความ/ตัวเลขลับ. ไม่แสดง ciphertext เต็มใน cell, dialog, tooltip, toast หรือ error. มีปุ่มเปิด token แบบตั้งใจเฉพาะ test/debug.
- Developer view เป็น read-only ใน aggregate/report/system; เขียนข้อมูลได้เฉพาะ flow ที่ API ตั้งใจเปิด เช่น test input/task. ห้ามใช้ mock record ที่ไม่ติดป้าย.
- สีสถานะของเอกสารและ prototype: เขียว `มี API จริง`, เหลือง `ใช้ mock`/ตัวอย่าง, แดง `ต้องสร้าง backend`. สีไม่ใช่สิ่งทดแทนข้อความ.
- ทุกหน้าต้องมี loading skeleton, empty state ที่ระบุว่าไม่มีข้อมูล, error พร้อม retry/request id ถ้ามี; error ห้าม echo request payload.

### 2.1 ภาพรวม `/`

**เป้าหมาย:** ตรวจเร็วว่า API-backed farm data ใช้งานได้และมีงาน/อากาศที่ต้องติดตาม; ไม่ใช้ dashboard เป็นหน้าโชว์ตัวเลขปลอม.

```text
┌────────────────────────────── ภาพรวม / DEVELOPER ───────────────────────────┐
│ ระบบ: API reachable?   role: developer     ข้อมูลลับ: masked                │
│ รอบปลูก active [จาก cycles]   งาน 7 วัน [จาก tasks]   อากาศวันนี้ [forecast]│
│ สถานะงาน: scheduler [ไม่มี API]   sensor [GET จริง]   backup [ไม่มี API]    │
│ [กราฟโดนัท: รอบปลูกตาม 5 สถานะ] [กราฟเส้น: อุณหภูมิสูงสุด/ต่ำสุด 7 วัน]    │
│ งานที่ใกล้ถึงกำหนด                 อากาศวันนี้ + ฝน                         │
│ masking smoke-check: customer/input/task → masked ✓ / ไม่ผ่าน / ยังไม่ตรวจ   │
└─────────────────────────────────────────────────────────────────────────────┘
```

| ส่วน | แหล่งข้อมูล / สถานะ | Owner vs developer | States / reuse / size |
|---|---|---|---|
| จำนวน cycle และสถานะ | `GET /crop-cycles` — **มี API จริง** | status/count เป็นข้อมูลที่อนุญาต; ชื่อพืช/รอบตาม response ปัจจุบัน | loading/empty/error; reuse FarmPlots; M |
| กราฟโดนัท: cycle ตาม 5 สถานะ | นับจาก `GET /crop-cycles` — **มี API จริง** | สถานะ/จำนวนเป็นข้อมูลที่อนุญาต; ทั้ง owner/developer เห็นเหมือนกัน | ใช้ Chart.js `DoughnutChart`; legend ภาษาไทยครบ 5 สถานะ; no-data/error state; M |
| งานที่ครบกำหนด | `GET /tasks?status=pending&from=&to=` — **มี API จริง** | Owner title จริง; developer manual title เป็น label masked, auto title ปกติ | reuse TaskWidget แบบตัดปุ่ม owner-only; S |
| อากาศวันนี้/7 วัน | `GET /weather/forecast?days=7` — **มี API จริง** | ข้อมูล weather ไม่ใช่ข้อมูลลับ | reuse WeatherWidget แบบ compact; M |
| กราฟเส้น: temp min/max 7 วัน | ใช้ค่าจาก `GET /weather/forecast?days=7` — **มี API จริง** | ทั้งสอง role เห็นได้; อย่าตีความเป็นข้อมูล sensor | ใช้ Chart.js `LineChart`, ป้ายวันภาษาไทย; ฝนวันนี้แสดงเป็น KPI แยก; M |
| ตัวเลขการเงิน | ไม่มี transaction/revenue API — **ต้องสร้าง backend (Phase 2)** | developer เห็น `ข้อมูลเข้ารหัส`; ห้ามวาดกราฟค่าจริงหรือใช้ mock | ไม่ใส่ chart ใน Dashboard ตอนนี้; แสดงสถานะ unavailable/masked เท่านั้น |
| สถานะ API, scheduler, last run, backup | `/system/health`, `/system/jobs`, `/system/backups` — **ต้องสร้าง backend (Phase 3)** | แสดง `ยังตรวจไม่ได้` จน API มี; ห้ามดึงข้อมูล filesystem/secret เข้า browser | error/unknown เป็น state จริง; L |
| ForecastSnapshot vs WeatherLog | `/weather/history` มี แต่ไม่มี endpoint อ่าน snapshots/เปรียบเทียบ — **ต้องสร้าง backend (Phase 2/3)** | aggregate ที่ไม่เปิดข้อมูลลับ | เว้น panel พร้อม label ว่ายังไม่มีข้อมูลเปรียบเทียบ; L |

**ของเดิม:** ลบ/ซ่อน StatCard ที่ใช้ตัวเลข hardcode, RevenueChart และ latestHarvest/low stock mock; customer preview ย้ายไป Partners. แทน PlotChart mock ด้วยกราฟโดนัทจาก `/crop-cycles` และแทน RevenueChart mock ด้วยกราฟเส้นอุณหภูมิจาก `/weather/forecast` เท่านั้น. Dashboard เหลือ KPI, 2 กราฟ, TaskWidget และ weather summary ที่มีแหล่งข้อมูลจริง; ไม่ทำให้ตัวเลขการเงินที่ยังไม่มี API กลายเป็นกราฟ.

### 2.2 ฟาร์ม `/farm/cycles`, `/farm/cycles/:id`, `/farm/activities`

**เป้าหมาย:** เป็นบ้านของโต๊ะ/รอบปลูก, status history, ผลผลิต และ task; คง PlotDetail/การบันทึกปุ๋ยเดิม ไม่เปลี่ยน state 5 ขั้นให้กลายเป็น activity.

```text
┌──────────────────────── ฟาร์ม ──────────────────────────────────────────────┐
│ [รอบปลูก] [กิจกรรม]                                      [+ เพิ่มรอบ]      │
│ ค้นหา cycle/table/crop     status chips                                  │
│ รอบ | โต๊ะ | crop | วันเริ่ม | สถานะ | ผลผลิต                             │
│ ─ เลือกรอบ → รายละเอียด / timeline / input history / บันทึกปุ๋ย-ยา ───────│
│ กิจกรรม: due date | status | source | cycle | [ข้อมูลเข้ารหัส]              │
└─────────────────────────────────────────────────────────────────────────────┘
```

| ส่วน | แหล่งข้อมูล / สถานะ | Owner vs developer | States / reuse / size |
|---|---|---|---|
| รอบปลูก/reference | `/crop-cycles`, `/tables`, `/batches`, `/crop-types`, `/crop-cycles/{id}/status-log` — **มี API จริง** | ข้อมูลปัจจุบันไม่ใช่ข้อมูลลับตาม D2/D3 | reuse FarmPlots, PlotDetail, DataTable, StatusBadge; M |
| Activities/Task | `/tasks`, `/crop-cycles` — **มี API จริง** | manual title owner plaintext / developer masked; ไม่มีชื่อคนงานปัจจุบัน | reuse Activities; M |
| InputApplication | `/crop-cycles/{id}/input-applications`, `/input-applications/{id}`, `/input-catalog/suggestions` — **มี API จริง** | owner plaintext; developer ciphertext + `is_masked`, แสดง label สั้น | reuse PlotDetail/AutocompleteInput ชั่วคราว; M |
| ค่าใช้จ่ายงาน (พับเก็บ, default ปิด) | transaction/labor link — **ต้องสร้าง backend (Phase 2)** | owner กรอก/เห็นจริง; developer แสดง `ข้อมูลเข้ารหัส` สำหรับยอดรวม/รายการเงิน | UI shell ต้องแสดง `ตัวอย่าง` หากมี preview; L |

**D4 กระทบหน้า PlotDetail โดยตรง:** `InputItem.item_name` ปัจจุบันเป็นข้อความอิสระ + InputCatalog autocomplete. เมื่อตัด stock ต้องเปลี่ยนเป็น picker ที่ submit `product_id`, ยอดคงเหลือและหน่วย, แจ้ง stock ไม่พอ, มี `+ สร้างสินค้า` จาก flow เดียวกัน. InputCatalog ต้องกลายเป็น alias/cache ของ product เดียว ไม่สร้างรายชื่อปุ๋ยสองชุด. งาน backend Phase 2 ต้องถอดชื่อเดิมด้วย key ฝั่ง owner ใน migration เพื่อ match/create product และผูก `product_id`; **ยังไม่ลงรายละเอียด migration ใน blueprint**. ชื่อและจำนวนใช้ปุ๋ย/ยาต่อครั้งยังลับ; category/unit/stock balance เป็น plaintext ตาม D2/D3.

ยืนยันความเข้ากัน: Farm Plots/PlotDetail เดิมใช้ `/crop-cycles`, status log, InputApplication API อยู่แล้ว; ย้าย Activities และ Harvest เป็นแท็บ/สถานะของ cycle ไม่ต้องลบ route API เดิม. เก็บผลผลิตที่ `harvest_quantity_kg`; ปุ่ม harvest เดิมชี้ไป cycle `harvested`. ค่าเริ่มวันอังคารถัดไปยังคงอยู่และแก้ได้. `PlotDetail` ปัจจุบันมี “วัตถุดิบที่ใช้” hardcode placeholder; แทนด้วย movement/input rows เมื่อ backend พร้อม. หลักฐาน: [src/pages/FarmPlots.jsx](src/pages/FarmPlots.jsx), [src/pages/PlotDetail.jsx](src/pages/PlotDetail.jsx), [app/routers/crop_cycles.py](app/routers/crop_cycles.py), [app/routers/input_applications.py](app/routers/input_applications.py).

### 2.3 สภาพอากาศ `/weather`

**เป้าหมาย:** แยกการตรวจพยากรณ์, ค่ารายวันย้อนหลัง และ sensor ออกจากกัน; ไม่ทำให้ Recommendation/sensor ที่ยังว่างดูเหมือนพร้อมใช้.

```text
┌──────────────────────── สภาพอากาศ ────────────────────────────────────────┐
│ [วันนี้] [พยากรณ์ 7 วัน] [ย้อนหลัง]                         [อัปเดต]       │
│ วันนี้: min/max / humidity / rain / condition                              │
│ forecast 7 วัน: date | temp | humidity | precipitation                     │
│ History: API/model archive (ไม่ใช่ sensor ground truth)                     │
│ Sensor: ยังไม่มีข้อมูล / readings ที่ได้รับจริง                             │
│ Recommendation: ยังไม่มี API/rule engine                                    │
└─────────────────────────────────────────────────────────────────────────────┘
```

| ส่วน | แหล่งข้อมูล / สถานะ | Owner vs developer | States / reuse / size |
|---|---|---|---|
| วันนี้และ forecast 7 วัน | `GET /weather/forecast?days=7` — **มี API จริง** | เหมือนกันทั้งสอง role | reuse WeatherWidget; M |
| ย้อนหลัง | `GET /weather/history?from=&to=` — **มี API จริง** | เหมือนกัน | empty/error/date range; ต้องเพิ่มหน้า/ตาราง, M |
| ข้อจำกัดของ history | WeatherLog ถูกดึงจาก Open-Meteo forecast API สำหรับวันที่ผ่านมา; handoff ระบุเป็น archived/model-based value ไม่ใช่ค่าตรวจจาก sensor ที่ฟาร์ม | แสดง source/คำอธิบายให้ developer เห็นชัด | หลักฐาน [Project-Phase/erp-farm-pi-weather-collection-handoff-2026-10-31.md](Project-Phase/erp-farm-pi-weather-collection-handoff-2026-10-31.md) และ [app/services/weather.py](app/services/weather.py) |
| ForecastSnapshot | มีตารางและ job capture แต่ไม่มี read endpoint/UI — **ต้องสร้าง backend (Phase 2)** | เทียบ forecast กับค่าผ่านมาได้ แต่ยังไม่ใช่ sensor truth | อย่าแสดงกราฟเทียบจนมี read API; M-L |
| Sensor | `GET /sensors/readings?sensor_type=&from=&to=&limit=` — **มี API จริง**; ingestion `POST` ใช้ `X-Device-Token` | developer เห็น readings ตาม API; token ของ device ห้ามส่ง browser | empty “ยังไม่มี readings”; reuse chart wrappers; M |
| Recommendation | model/table เท่านั้น ไม่มี API, rule engine หรือ UI — **ต้องสร้าง backend (Phase 2)**; ต้องรวมกับ Insight | ห้ามโชว์คำแนะนำปลอม | วาง empty placeholder ชัดเจน; S (shell) / L (logic) |

API refs: [app/routers/weather.py](app/routers/weather.py), [app/routers/sensors.py](app/routers/sensors.py), `capture_forecast_snapshots` ใน [app/services/weather.py](app/services/weather.py), scheduler ใน [app/main.py](app/main.py).

### 2.4 สินค้า & คลัง `/products`

**เป้าหมาย:** รายการสินค้าและยอดคงเหลือที่ตรวจได้; ตารางเดียวมี filter ตาม `category`, รายละเอียดมี movement พร้อมต้นทาง. UI จริงรอ backend.

```text
┌──────────────────────── สินค้า & คลัง ────────────────────────────────────┐
│ [ทั้งหมด] [ผัก] [เมล็ด] [ปุ๋ย] [ยา] [ปุ๋ยผสม]  ค้นหา*     [+ เพิ่มสินค้า] │
│ ชื่อ             ประเภท   คงเหลือ   หน่วย   จุดสั่งซื้อ  สถานะ              │
│ [รายละเอียดเมื่อเลือกแถว: current balance | movement timeline | source]     │
│                                             [ปรับยอดตามนับจริง]             │
└─────────────────────────────────────────────────────────────────────────────┘
```

| ส่วน | แหล่งข้อมูล / สถานะ | Owner vs developer | States / reuse / size |
|---|---|---|---|
| Product, stock, movement, search/filter, low-stock | ยังไม่มี endpoint/model สินค้า — **ต้องสร้าง backend (Phase 2)** | Owner เห็นชื่อจริง; developer: ชื่อปุ๋ย/ยา/ปุ๋ยผสมเป็น `ข้อมูลเข้ารหัส`, stock balance/category/unit คง plaintext | ห้ามโชว์ mock เป็นจริง; empty state บอกยังไม่มี backend; L |
| Movement detail | StockMovement ที่ผูก source type/id — **ต้องสร้าง backend (Phase 2)** | ชื่อ/จำนวน input ของปุ๋ยและสูตรลับต้อง masked; แสดงประเภท/วันที่/ยอดคงเหลือ plaintext | movement ต้องแสดงที่มา (รับเข้า, ส่งออก, input application, adjustment); L |
| Create/edit | ยังไม่มี API — **ต้องสร้าง backend (Phase 2)** | input fields ตาม D2/D3 | reuse Modal/DataTable หลังเพิ่ม empty/loading; M-L |

หมายเหตุประเภทสินค้า: ผักที่ไม่เก็บ stock แสดงเป็นสินค้าขายและ stock เป็น “ไม่นับ”; เมล็ดยังถือว่าชื่อไม่ลับเป็น **สมมติฐานรอ owner ยืนยัน**; ห้าม seed product/input names. การค้นชื่อปุ๋ย/ยาโดย developer ต้องไม่ถอดรหัสใน client; backend ที่ได้รับสิทธิ์เท่านั้นกรองหลัง decrypt.

### 2.5 รับเข้า / ส่งออก `/trade/inbound`, `/trade/outbound`

**เป้าหมาย:** ใช้ form/list component เดียวเปลี่ยน direction; inbound เลือก supplier, outbound เลือก customer และอาจมี delivery location/contract.

```text
┌────────────────────── รับเข้า / ส่งออก ────────────────────────────────────┐
│ [รับเข้า] [ส่งออก]    date range | คู่ค้า | สินค้า                           │
│ วันที่ | คู่ค้า/ข้อมูลเข้ารหัส | รายการ | จำนวน/ข้อมูลเข้ารหัส | สถานะ     │
│ + บันทึกรายการ                                                               │
│ ฟอร์ม: วันที่ / คู่ค้า + เพิ่มใหม่ / สินค้า / จำนวน / หน่วย / note          │
│ outbound only: ราคา / delivery location / contract-order (Phase 2)           │
└─────────────────────────────────────────────────────────────────────────────┘
```

| ทิศทาง / ฟิลด์ | API/data status | Masking | ขนาด |
|---|---|---|---|
| รับเข้า: date, supplier, product, quantity, unit, private note | ไม่มี supplier/purchase API — **ต้องสร้าง backend (Phase 2)** | supplier, note, input name/quantity เป็นข้อมูลลับ; category/unit/date/stock balance plaintext | L |
| ส่งออก: date, customer, product, quantity, price, location, note | `/customers` มีแค่ customer CRUD; ไม่มี order/sales API — **ต้องสร้าง backend (Phase 2)** | customer/location/contact/note/price/revenue และชื่อปุ๋ยผสม masked; quantity เปิดตาม policy | L |
| เลือก/เพิ่มคู่ค้า | Customer `GET/POST/DELETE /customers` — **มี API จริง**; Supplier API ไม่มี — **ต้องสร้าง backend (Phase 2)** | dropdown แสดง owner plaintext; developer เห็น label `ข้อมูลเข้ารหัส` โดยไม่เผย token; create inline มี safe confirmation | M |
| Stock side effect | StockMovement ไม่มี — **ต้องสร้าง backend (Phase 2), ระดับ A** | movement value ตาม rule D3 | Must be transactionally linked; L |
| Contract/Order | ยังไม่เริ่ม — **ต้องสร้าง backend (Phase 2)** | ลูกค้าและ delivery_location เป็นข้อมูลคน/สถานที่ลับ | M-L |

**พื้นที่และราคา:** เจ้าของต้องการดูราคาตามพื้นที่ แต่การจัดกลุ่มสถานที่ให้ backend decrypt/filter เท่านั้น; developer ได้ aggregate ใหม่แบบ encrypted + `is_masked`, ห้ามส่งราคา/aggregate เดิมหรือค่าประมาณ. ต้องเก็บ `delivery_location` เป็น field แยก ไม่ encode ใน note.

### 2.6 การเงิน `/finance`, `/finance/reports`

**เป้าหมาย:** คำนวณจากเหตุการณ์ซื้อ/ขาย/ค่าแรง/ค่าใช้จ่าย ไม่ให้กรอกยอดซ้ำในหน้า dashboard.

```text
┌──────────────────────── การเงิน ───────────────────────────────────────────┐
│ [ไตรมาส] [ฤดู] [ช่วงวันที่] [พื้นที่*]                                      │
│ รายรับ | ต้นทุน | ค่าแรง | รายจ่ายอื่น | กำไรสุทธิ                          │
│ trend price by period/area       revenue by customer                        │
│ แหล่งที่มา: inbound / outbound / task expense / labor / other expense       │
│ developer view: [ข้อมูลเข้ารหัส] × 5  + สถานะการ mask (ไม่ render ตัวเลข)   │
└─────────────────────────────────────────────────────────────────────────────┘
```

| Metric | สูตร/ต้นทาง | สถานะ API | Developer display |
|---|---|---|---|
| รายรับ | ผลรวมราคาจากส่งออก/order lines | **ต้องสร้าง backend (Phase 2)** | ค่า owner จริง; developer token aggregate ใหม่ + `is_masked`, UI แสดง `ข้อมูลเข้ารหัส` |
| ต้นทุนซื้อ | ราคาจากรับเข้า | **ต้องสร้าง backend (Phase 2)** | mask เช่นเดียวกัน |
| ค่าแรง | LaborLog (`worker_count`, hours, job type, encrypted amount) | **ต้องสร้าง backend (Phase 2)** | mask ยอด; หลีกเลี่ยงชื่อ worker หรือเข้ารหัสชื่อ worker |
| รายจ่ายจาก Task | transaction link กลับ Task | **ต้องสร้าง backend (Phase 2)** | masked amount/title attribution; task manual title masked |
| รายจ่ายเบ็ดเตล็ด | Transaction type expense | **ต้องสร้าง backend (Phase 2)** | masked amount; owner input only |
| กำไร/ขาดทุน | รายรับ − ต้นทุนซื้อ − ค่าแรง − รายจ่ายอื่น | **ทำไม่ได้จาก API ปัจจุบัน** | backend คำนวณหลัง decrypt แล้วเข้ารหัส aggregate ใหม่; ห้ามคำนวณจากตัวเลขที่ส่งมา |
| ราคาแยกไตรมาส/ฤดู/พื้นที่ | outbound prices + delivery_location | **ต้องสร้าง backend (Phase 2)** | แสดง encrypted aggregate; ไม่แสดงกราฟ shape/value ที่ย้อนเดาได้ |
| เทียบรายได้ต่อลูกค้า | outbound/customer links | **ต้องสร้าง backend (Phase 2)** | ห้ามแสดง label/customer identity/amount; แสดงสถานะข้อมูลเข้ารหัส |

ตัวเลขการเงินทุกชนิด (รวมต้นทุน, ซื้อ, ค่าแรง) ให้ถือเป็นข้อมูลลับสำหรับ wireframe จน owner ยืนยันข้อเสนอ. มี secure helpers แต่ไม่มี transaction data: [app/services/secure_fields.py](app/services/secure_fields.py), Phase 2 ใน [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md).

### 2.7 คู่ค้า `/partners/suppliers`, `/partners/customers`

**เป้าหมาย:** แยกข้อมูลคู่ค้าจาก Overview; เลือกคู่ค้าใน inbound/outbound ได้โดยไม่ต้องเปิดอีกหน้าค้าง.

```text
┌──────────────────────── คู่ค้า ────────────────────────────────────────────┐
│ [ซัพพลายเออร์] [ลูกค้า]   search (owner)              [+ เพิ่มคู่ค้า]       │
│ ชื่อ/ข้อมูลเข้ารหัส | ช่องทางติดต่อ/ข้อมูลเข้ารหัส | ที่อยู่/ข้อมูลเข้ารหัส │
└─────────────────────────────────────────────────────────────────────────────┘
```

| Tab | Data status | Presentation / reuse | Size |
|---|---|---|---|
| ลูกค้า | `GET/POST/DELETE /customers` — **มี API จริง**; ไม่มี PATCH | reuse CustomerPanel form/list, ย้ายออก Dashboard, เพิ่ม `is_masked` shared display และ safe delete confirm | S-M |
| ซัพพลายเออร์ | ไม่มี model/endpoint — **ต้องสร้าง backend (Phase 2)** | ชื่อ, contact, ที่อยู่, note เป็นข้อมูลคน/ข้อมูลลับตาม D2; developer เห็น label masked | M-L |
| เพิ่มจาก trade form | customer API มี; supplier API ไม่มี | inline drawer/modal แล้วกลับไปยัง trade form โดยรักษาค่าที่กรอก | M |

### 2.8 ตั้งค่าและผู้ใช้ `/settings/profile`, `/settings/users`

**เป้าหมาย:** เก็บการแก้โปรไฟล์/จัดการบัญชีไว้ชั้นรอง ไม่ปะปนกับงานฟาร์ม; ไม่แสดงรายชื่อผู้ใช้ mock.

```text
┌──────────────────────── ตั้งค่า (owner only) ──────────────────────────────┐
│ [โปรไฟล์] [ผู้ใช้]                                                         │
│ โปรไฟล์: ยังไม่มี settings API                                             │
│ ผู้ใช้: ยังไม่มี user-management API; ไม่แสดง mock roster                   │
│ Developer: ไม่มีสิทธิ์หน้า settings; ไปที่ /developer/system               │
└─────────────────────────────────────────────────────────────────────────────┘
```

| ส่วน | API status | Role / state / reuse / size |
|---|---|---|
| Profile | ไม่มี — **ต้องสร้าง backend (Phase 4 ตาม roadmap)** | owner-only; developer direct URL ได้ access-denied state; S shell, M เมื่อมี API |
| Users | ไม่มี user-management endpoint — **ต้องสร้าง backend (Phase 4)** | อย่าใช้ `userData`; owner-only; loading/empty/error แยกจาก mock; L เมื่อมี permission lifecycle |
| Developer route | `/developer/system` เป็น route แยก | ไม่ redirect ไปหน้าที่อาจเปิดข้อมูล owner; แสดงสิทธิ์ไม่เพียงพอหรือกลับหน้าสถานะระบบ |

หลักฐาน: `/users` และ `/settings` ปัจจุบันเป็น routes แต่ `Users` ใช้ mockData และ `Settings` เป็น placeholder; ดู [src/App.jsx](src/App.jsx), [src/pages/Users.jsx](src/pages/Users.jsx), [src/pages/Settings.jsx](src/pages/Settings.jsx), [app/main.py](app/main.py#L104-L111).

### 2.9 สถานะระบบ `/developer/system` (เฉพาะ developer)

**เป้าหมาย:** ตรวจขอบเขต masking, data hooks และ operational state โดยไม่สร้างความรู้สึกว่า endpoint ที่ไม่มีอยู่แล้ว.

```text
┌──────────────────────── สถานะระบบ / DEVELOPER ────────────────────────────┐
│ API auth [ทดสอบจาก request]    app version [ยังไม่มี endpoint]              │
│ Weather jobs: 08:00 / 08:05 registered in code; last-run [ยังไม่มี API]     │
│ WeatherLog [GET จริง]      ForecastSnapshot [read API ไม่มี]                 │
│ SensorReading [GET จริง]   Recommendation [API/UI ไม่มี]                     │
│ Backup/restore health [ไม่มี endpoint; ห้ามสรุปจากไฟล์ browser]             │
│ Mask checks: customer / manual task / input item / numeric aggregate          │
│ token preview: เฉพาะ action ทดสอบ; ย่อและไม่ใส่ใน toast/log                  │
└─────────────────────────────────────────────────────────────────────────────┘
```

| Check | API status | ตีความ |
|---|---|---|
| Weather forecast/history | `GET /weather/forecast`, `/weather/history` — **มี API จริง** | ตรวจการตอบของ service ได้ แต่ไม่เท่ากับ scheduler run ล่าสุด |
| Job registration | APScheduler jobs ถูก register ใน `app/main.py` — มีใน code; **ไม่มี API จริงสำหรับ job status/last run** | แสดง “ตั้งค่าใน code; runtime ยังตรวจไม่ได้” จนสร้าง API |
| ForecastSnapshot | model/table และ capture service มี — **ไม่มี read API** | ห้ามใช้ count จาก frontend |
| Sensor readings | `GET /sensors/readings` — **มี API จริง** | empty ไม่เท่ากับ sensor เสีย; แสดงเวลาล่าสุดเมื่อมี record |
| Device ingest | `POST /sensors/readings` ใช้ `X-Device-Token`; ถ้าไม่ตั้ง token จะ 503 | ห้ามเปิด token ให้ browser/user; อย่าแสดง secret หรือขอให้ copy secret |
| Backup/restore | migration ทำ backup แต่ operational backup/restore API ไม่พบ — **ต้องสร้าง backend/ops (Phase 3)** | UI แสดง “ตรวจไม่ได้จากแอป” ไม่แสดง success สีเขียว |
| Recommendation | ตารางว่าง; ไม่มี API/engine/UI | รวมกับ Insight ก่อน Phase 2; ห้ามเรียก rule-based ว่า AI |
| Error hygiene | API helper แปลง detail เป็น Error; validation handler ควรไม่ echo body ตาม Phase 1e | test 422/404/500 โดยใช้ synthetic payload และตรวจไม่มี token/secret ในข้อความ |

ขนาด: M สำหรับหน้า read-only ที่ใช้ API จริง, L เมื่อเพิ่ม health/jobs/snapshot/backup endpoints. Evidence: [app/main.py](app/main.py), [app/models.py](app/models.py), [app/routers/weather.py](app/routers/weather.py), [app/routers/sensors.py](app/routers/sensors.py), [Project-Phase/erp-farm-phase1e-input-masking-data-hooks-prompt.md](Project-Phase/erp-farm-phase1e-input-masking-data-hooks-prompt.md).

## 3. Navigation และโครงสร้างโค้ด

### 3.1 Nav config เดียว

ตัวอย่างข้อมูลที่ Sidebar, top menu, mobile companion และ route metadata อ่านร่วมกัน; mobile order เป็น contract สำหรับ agent ฝั่งมือถือ ไม่ใช่การออกแบบหน้ามือถือใน scope นี้.

```js
export const navigation = [
  { id: 'overview', label: 'ภาพรวม', path: '/', icon: 'LayoutDashboard', group: 'main', roles: ['owner', 'developer'], mobileOrder: 1 },
  { id: 'farm', label: 'ฟาร์ม', path: '/farm/cycles', icon: 'Sprout', group: 'main', roles: ['owner', 'developer'], mobileOrder: 2, tabs: ['cycles', 'activities'] },
  { id: 'weather', label: 'สภาพอากาศ', path: '/weather', icon: 'CloudSun', group: 'main', roles: ['owner', 'developer'], mobileOrder: null },
  { id: 'products', label: 'สินค้า & คลัง', path: '/products', icon: 'Boxes', group: 'main', roles: ['owner', 'developer'], mobileOrder: 4 },
  { id: 'trade', label: 'รับเข้า / ส่งออก', path: '/trade/inbound', icon: 'ArrowLeftRight', group: 'main', roles: ['owner', 'developer'], mobileOrder: 3, tabs: ['inbound', 'outbound'] },
  { id: 'finance', label: 'การเงิน', path: '/finance', icon: 'Wallet', group: 'main', roles: ['owner', 'developer'], mobileOrder: 5 },
  { id: 'partners', label: 'คู่ค้า', path: '/partners/customers', icon: 'Users', group: 'master-data', roles: ['owner', 'developer'], mobileOrder: null },
  { id: 'settings', label: 'ตั้งค่า', path: '/settings/profile', icon: 'Settings', group: 'master-data', roles: ['owner'], mobileOrder: null },
  { id: 'system', label: 'สถานะระบบ', path: '/developer/system', icon: 'Activity', group: 'developer', roles: ['developer'], mobileOrder: null },
];
```

เมนู 6 หลักคง 4 module ที่ปรึกษาต้องเห็นชัดผ่าน Products & stock และ Inbound/Outbound tab. `Farm` รวม cycle/activity; Harvest ไม่เป็นเมนูหลักซ้ำ. สภาพอากาศอาจเปิดจาก weather widget/เมนูบน. Developer system อยู่เมนูรองเฉพาะ developer.

### 3.2 Redirect และ nested routes

Redirect มีไว้รักษา deep link/bookmark; query string ควรถูกคงเมื่อทำได้. ทุก path เก่าต้องมีที่ไป ไม่ใช้ wildcard redirect แบบทำข้อมูลหาย.

| URL เดิม | URL ใหม่ |
|---|---|
| `/` | `/` |
| `/plots` | `/farm/cycles` |
| `/plots/:id` | `/farm/cycles/:id` |
| `/activities` | `/farm/activities` |
| `/harvest` | `/farm/cycles?status=harvested` |
| `/inventory` | `/products` |
| `/sales` | `/trade/outbound` |
| `/costs` | `/finance` |
| `/reports` | `/finance/reports` |
| `/users` | `/settings/users` (owner-only; developer ได้ access-denied state; ไม่มี user API) |
| `/settings` | `/settings/profile` (owner-only; developer ได้ access-denied state) |

โครง routes แนะนำ: `/farm` parent + `cycles`, `cycles/:id`, `activities`; `/trade` + `inbound`, `outbound`; `/finance` + `reports`; `/partners` + `customers`, `suppliers`; `/developer/system`. เก็บ redirect ใน route config กลาง.

### 3.3 โครงไฟล์ที่เสนอ

```text
src/
  app/navigation.js
  app/routes.jsx
  pages/overview/OverviewPage.jsx
  pages/farm/{CycleListPage,CycleDetailPage,ActivitiesPage}.jsx
  pages/weather/WeatherPage.jsx
  pages/products/ProductsPage.jsx
  pages/trade/{TradePage,TradeForm}.jsx
  pages/finance/{FinancePage,FinanceReportsPage}.jsx
  pages/partners/{PartnersPage,SupplierForm}.jsx
  pages/developer/DeveloperSystemPage.jsx
  components/security/{MaskedValue,MaskedAggregate,MaskStatus}.jsx
  components/{AppShell,EmptyState,ErrorState,LoadingState}.jsx
  components/charts/                         # Chart.js wrappers ที่มีอยู่
  features/{farm,weather,customers,tasks}/    # API hooks/query helpers ตาม pattern ที่เลือก
```

ไม่จำเป็นต้องย้ายทุกไฟล์ทันที: ใช้ wrapper/route alias ก่อน แล้วทยอยย้าย exports. `CustomerPanel` กลายเป็น section ของ `PartnersPage`; `TaskWidget` ใช้ใน Overview และ Farm; `WeatherWidget` ใช้ compact/full mode; `DataTable` ใช้เฉพาะ desktop และเพิ่ม card/list renderer เฉพาะ mobile app agent.

### 3.4 Pattern masking กลาง

- `<MaskedValue value isMasked label="ข้อมูลเข้ารหัส" allowReveal={false} />`: default เป็น label; explicit debug reveal แสดง token ที่ truncate/copy ได้ และไม่เอาไปสร้าง confirm/toast.
- `<MaskedAggregate isMasked>`: ไม่ render chart/แกน/tooltip จาก encrypted aggregate; แสดง count ของสถานะ mask ได้เมื่อ backend อนุญาต.
- `<MaskStatus checks={...} />`: แสดง pass/fail/unknown โดยใช้ synthetic records; ไม่ใช้ข้อมูลจริงของ farm.
- กรองข้อมูลลับที่ backend response boundary เท่านั้น. Search field ของ confidential name ส่ง query ไป backend; ห้าม filter ciphertext ใน browser.
- `api()` error mapping กลางต้องตัด raw body/request input; component ใช้ fixed copy สำหรับ confirm/delete/validation.

### 3.5 ผลกระทบต่อ tests/build

- Route tests: ทุก path เก่า redirect ไป route ใหม่; deep link PlotDetail/แท็บทำงาน; unknown route มี 404.
- Mask tests: owner plaintext; developer ทุก field ที่กำหนดเป็น masked; inspect dialog/toast/dropdown/tooltip/error รวม `CustomerPanel` regression.
- API contract tests สำหรับหน้าที่มี API; mock data test ต้องระบุคำว่า `ตัวอย่าง` และไม่แสดงใน production view.
- D4 tests: product picker ใช้ id, ปริมาณไม่พอ, unit conversion, movement source, edit/delete reversal, InputCatalog migration compatibility.
- D5 tests: cost optional collapsed, transaction links to task, task edit/delete changes linked transaction as agreed.
- `npm run build`; bundle check ไป temp output นอก workspace; browser check desktop widths (1280/1440), narrow 1024, keyboard/zoom, role developer.

## 4. Gap Analysis

| ข้อกำหนด/ความต้องการ | หน้ารองรับใน To-Be | สถานะ | สิ่งที่ขาด / หลักฐาน |
|---|---|---|---|
| งานที่ต้องทำ/แจ้งเตือน | Overview, Farm/Activities | ครอบคลุมบางส่วน | Tasks API/widget มีแล้ว; push/notification API ไม่มี. `TaskWidget`, `app/routers/tasks.py` |
| สภาพอากาศและพยากรณ์ละเอียด | Weather, Overview | ครอบคลุมบางส่วน | Live forecast/history มี; scheduled runtime, snapshot read, sensor ground truth ยังไม่ยืนยัน/ไม่มี API UI. `weather.py`, `sensors.py`, handoff |
| ย้อนดูรอบการผลิต/ผลผลิต | Farm/Cycle detail | ครอบคลุมบางส่วน | cycle/status log/harvest quantity มี; ปริมาณขาย/สูญเสีย/เชื่อม export ไม่มี. `crop_cycles.py`, `PlotDetail` |
| สัญญารายปี | Trade/Outbound | ยังไม่มี | Contract/Order เป็น Phase 2 |
| ราคาต่างตามพื้นที่/แนวโน้มราคา | Finance reports | ยังไม่มี | outbound price/location API และ encrypted aggregate ต้องสร้าง Phase 2 |
| ต้นทุน/รายได้/กำไร | Finance | ยังไม่มี | Transaction, encryption fields, labor, backend aggregation Phase 2 |
| ค่าแรง/จำนวนคน/ชั่วโมง/ประเภทงาน | Finance, Task form attribution | ยังไม่มี | LaborLog Phase 2; worker count + hours + job type ตาม PROJECT_CONTEXT |
| เปรียบเทียบรายได้ต่อลูกค้า | Finance reports | ยังไม่มี | backend grouping หลัง decrypt + encrypted aggregate Phase 2 |
| 4 ERP modules: สินค้า/คลัง/รับเข้า/ส่งออก | Products; Trade tabs | ยังไม่มี API | label ชัดตามข้อกำหนด; model/API Phase 2 |
| D1 owner mobile / developer desktop | Scope boundary | ครอบคลุมในแผน | owner-mobile ทำ wireframe อีกชุด; nav config ควรใช้ชื่อ/path ร่วม |
| D2 ข้อมูลคน/สถานที่ต้อง mask | Partners, Trade | ครอบคลุมบางส่วน | customer API mask มี; supplier/location APIs ยังไม่มี; confirm dialog customer เสี่ยง leak |
| D3 ชื่อปุ๋ย/ยาและ note ลับ; ปริมาณเปิด | Farm, Products, Trade | ครอบคลุมบางส่วน | Phase 1e ปัจจุบันยัง encrypt quantity; ต้องถอดรหัส/migrate พร้อม D4 และส่งตัวเลขจริงให้ developer; stock/product/trade schema ยังไม่มี |
| D4 สต็อกอัตโนมัติทุกจุด | Products, Trade, Farm | ยังไม่มี | StockMovement, product id, unit conversion, adjustment workflow; InputCatalog อาจกลายเป็นรายชื่อซ้ำ |
| D5 การเงิน optional ใน Task | Farm/Activities, Finance | ยังไม่มี | Transaction/LaborLog link และ delete/edit behavior Phase 2 |
| Phase 2 Contract/Order | Trade | ยังไม่มี | `delivery_location`, relationship, price per area |
| Phase 2 StockItem | Products/Stock | ยังไม่มี | ต้องทบทวน StockItem ให้เป็น source of truth สำหรับ movement |
| Phase 2 Transaction/LaborLog/Reports | Finance | ยังไม่มี | schema/API/crypto/aggregate |
| Phase 2 ข้อ 6 Insight + Recommendation | Weather/Overview | ครอบคลุมบางส่วน | Recommendation model มี แต่ต้องรวม Insight เป็น resource เดียวก่อน API/UI |
| Phase 3 Pi/deploy/backup | Developer System | ยังไม่มีใน UI/API | health/job/backup/restore metrics และ operational procedures |
| Phase 4 Flutter | นอก scope frontend desktop | ยังไม่เริ่ม | responsive web/PWA ทดลองได้ แต่ไม่แทน native requirements โดยอัตโนมัติ |
| Phase 5 AI | Recommendation slot | ยังไม่มี | เริ่มหลัง Phase 4; ห้ามเรียก rule-based ว่า AI |

### ของเดิมที่ควรย้าย/ซ่อน/ยกเลิก

| หน้า/ปุ่มเดิม | แนวทาง | เหตุผล |
|---|---|---|
| Harvest | ย้ายเป็น filter/state ของ Farm cycle; ใช้ `harvest_quantity_kg` | ไม่สร้างหน้าผลผลิต mock ซ้ำ; ส่งต่อ outbound ภายหลัง |
| Inventory | ย้ายเป็น Products & stock shell; ซ่อนค่าจำลอง | ไม่มี backend; ทำให้เข้าใจผิดว่าคงเหลือจริง |
| Sales | ย้ายเป็น Outbound shell; ซ่อน demo orders/amounts | ยังไม่มี Order/Transaction API และมีข้อมูลคน/ยอดเงินที่ต้อง mask |
| Costs | ย้ายเป็น Finance shell | ไม่มี Transaction/LaborLog; ห้ามใช้ตัวเลข mock |
| Reports | ย้ายเป็น Finance reports tab และแสดง unavailable state | ไม่มี data/report API |
| Users | ซ่อนหรือเป็น system configuration page เมื่อมี API | `userData` เป็น mock roster และไม่มี user admin API |
| Navbar search/bell | ซ่อนจนมี search scope/notification backend | controls ปัจจุบันไม่มี behavior/API |
| Dashboard customer panel | ย้ายไป Partners | ลดความแน่นของ Overview; ปิด dialog leak ก่อน reuse |
| Dashboard revenue/stock mock cards | ลบจาก production view | ข้อมูลจำลองและข้อมูลลับทางการเงิน |

## 5. Implementation Slices

ขนาดโดยประมาณสำหรับทีม 2 คน; acceptance ต้องตรวจได้. “ไม่พึ่ง backend” หมายถึงใช้ API จริงที่มีหรือจัด layout/route เท่านั้น ไม่สร้าง mock ปลอมในหน้าจอ production.

### ทำก่อนเดโม

| ลำดับ / ชิ้นงาน | ไฟล์ที่แตะในอนาคต | ขนาด / Backend | Acceptance criteria และวิธีทดสอบ |
|---|---|---|---|
| 1. Nav config, responsive shell, redirect | `src/App.jsx`, `src/layouts/*`, `src/components/{Sidebar,Navbar}.jsx`, `src/data/navigation.js` | M / ไม่พึ่ง backend | ทุก route เก่ามี redirect; deep link เปิดได้; sidebar ใช้ config เดียว; desktop keyboard nav; browser เช็ก 1280/1024 และ 404 |
| 2. Farm รวม cycles/detail/activities | `src/pages/FarmPlots.jsx`, `PlotDetail.jsx`, `Activities.jsx`, route config | M / ใช้ API จริง | CRUD รอบปลูกและ tasks ยัง persist; status log แสดง; วันอังคารถัดไปยังแก้ได้; masked title/input ไม่มี token leak; tests + browser developer role |
| 3. Weather page + history | เพิ่ม `WeatherPage.jsx`; reuse `WeatherWidget`; API client | M / ใช้ `/weather/*`; sensor GET จริง | forecast/history แสดง source/date; error/retry/empty; ระบุ history ว่า model-based ไม่ใช่ sensor; browser ตรวจข้อมูลจริงและ responsive |
| 4. Overview ลด mock | `Dashboard.jsx`, `TaskWidget.jsx`, `WeatherWidget.jsx`, charts | M / API จริง | ไม่มี mock amount/revenue/harvest/stock; cards จาก APIs จริง בלבד; TaskWidget masked; failed endpoint ไม่ถูกตีเป็น zero; tests + browser |
| 5. Partners: Customer API | `CustomerPanel.jsx`, `PartnersPage.jsx`, shared masking | S-M / Customer API จริง | customer moved from dashboard; developer no full token in confirm/toast/error; owner search/add/delete; regression test using synthetic customer |
| 6. Developer System read-only shell | `DeveloperSystemPage.jsx`, `MaskStatus.jsx` | M / ใช้ Weather/Sensor APIs จริง; job/backup/snapshot status unavailable | ทุก unavailable status แสดง “ยังไม่มี API/ตรวจไม่ได้”; sensor GET มี empty/error; ไม่มี credential/log secret; browser/API contract test |
| 7. Placeholder Products/Trade/Finance | `ProductsPage.jsx`, `TradePage.jsx`, `FinancePage.jsx` | S-M / backend ไม่พร้อม | ไม่แสดงตัวเลข/record แสร้งเป็นจริง; ทุกตัวอย่างติด badge `ตัวอย่าง`; 4 module labels ชัด; CTA บอก backend phase |

### หลังเดโม / ทำเมื่อมีเวลา (ตาม dependency)

| ลำดับ / ชิ้นงาน | ไฟล์/Backend | ขนาด | Acceptance criteria |
|---|---|---|---|
| 8. Decision record: Product + StockMovement + InputCatalog | Phase 2 spec/model | M / ต้องตัดสินใจก่อน backend | product เป็นแหล่งเดียว; input เก่าผูก product id; movement มี source type/id; unit conversions และ reversal/soft-delete behavior ถูกระบุ |
| 9. Stock ระดับ A | backend `StockItem/StockMovement`, input application, inbound/outbound, adjustment APIs; frontend picker/detail | L / Phase 2 | inbound +, outbound −, input use −, adjustment ± ผ่าน movement; edit/delete reverses correctly; insufficient-stock rule; no direct balance mutation; tests migration/API/UI |
| 10. Stock ระดับ B | CropCycle/seed quantity fields + movement service | M-L / Phase 2 | seed stock deducted on cycle start only with explicit seed count; count/unit conversion tested; optional legacy value handling |
| 11. Stock ระดับ C: ใบผสม | formula/production batch model/API + encrypted formula UI | L / Phase 2 | component inputs − and blended product +; recipe encrypted; duplicate submit idempotent; movement provenance complete |
| 12. Trade + partner supplier + contracts/orders | API/model, `TradePage`, supplier/customer forms | L / Phase 2 | inbound/outbound linked to partner/product; `delivery_location` separate; confidential fields masked; pricing group by area runs backend-only |
| 13. Finance + D5 Task expense | Transaction/LaborLog/API, Activities/Finance | L / Phase 2 | calculations trace to source; optional expense section collapsed by default; edit/delete linkage specified and tested; encrypted amounts and aggregates; no duplicate-entry form |
| 14. ForecastSnapshot/Recommendation UI hooks | snapshot read/comparison, one Recommendation/Insight resource | M-L / Phase 2 | separate API/model history from WeatherLog; source/version metadata; status states; no AI claims; no inference from model history called sensor truth |
| 15. Operational health + backup UI | health/jobs/backup/restore APIs and deployment integration | L / Phase 3 | last success/failure timestamps, retention/restore verification; browser shows unknown on missing API; secrets never returned |
| 16. PWA evaluation | manifest/icons/install verification; separate from Flutter | S-M / no backend | install to home screen on target phones, safe-area and responsive task flows work; document offline/push/native limits; Flutter remains Phase 4 |

**ถ้าเวลาบีบ:** ตัด chart trends, sensor graphs, PWA polish และ admin users/settings ก่อน; ไม่ตัด masking, real-data labels, task/weather access, stock-source model decision, or safe confirmation. Level A comes before B/C. B requires seed count per cycle (missing now); C requires encrypted recipe and mixing event (new model). “Automatic stock” only correct when source events are complete: retain explicit `ปรับยอดตามนับจริง` that records a movement, not an edit to balance. Units such as kg/g and L/ml need canonical conversion. Harvest quantity vs outbound amount can later estimate waste but is not a stock ledger by itself.

## 6. ข้อความเสนอแก้เอกสารสถานะ (ยังไม่แก้ไฟล์ต้นทาง)

### เสนอเพิ่มใน `PROJECT_STATUS.md`

```text
Frontend audit (2026-10-31): production มี React/Vite app เดียว; current routes and API/mock matrix อยู่ใน FRONTEND_BLUEPRINT-developer-desktop.md. Dashboard, Harvest, Inventory, Sales, Costs และ Users ยังใช้ mock/placeholder; ห้ามใช้ตัวเลขเหล่านี้เป็นข้อมูลจริง. Responsive shell ยังไม่เหมาะกับมือถือ: sidebar ยุบขนาดแต่ไม่เป็น drawer และตารางหลายหน้าต้องเลื่อนแนวนอน.

Masking UI follow-up: CustomerPanel.handleDelete ต้องไม่ส่ง customer.name เข้า confirm dialog; audit dialog/toast/error/dropdown ทุกจุดด้วย synthetic data. Developer UI แสดง label “ข้อมูลเข้ารหัส” เป็น default และไม่แสดง ciphertext เต็มใน dialog/toast/error.

Phase 2 frontend contract: เมนูหลัก 6 กลุ่มตาม blueprint; Products/Stock, Inbound/Outbound, Finance และ Supplier เป็น backend-pending shells เท่านั้น. ก่อน backend stock ให้ตัดสิน StockMovement/product_id/InputCatalog และหน่วยมาตรฐาน. รวม Recommendation กับ Insight เป็น resource เดียวก่อนกำหนด API/UI.

Weather UI ต้องแยก ForecastSnapshot, WeatherLog และ SensorReading; WeatherLog จาก Open-Meteo past-days เป็น model/archive value ไม่ใช่การวัดจริง ณ ฟาร์ม. Scheduler last-run, ForecastSnapshot read และ backup status ไม่มี UI/API ตรวจได้ในปัจจุบัน.
```

### เสนอปรับ `PROJECT_CONTEXT.md`

```text
เพิ่ม D1-D5 เป็นข้อกำหนด UI/data: owner ใช้มือถือเป็นหลัก; developer desktop เห็น masked data; customer/supplier/worker/location/contact, fertilizer/medicine/blended-product names และ free-text notes เป็นข้อมูลลับ; application quantity/stock balance/category/unit/date เปิดหลัง D4 migration/API contract; inventory counts are not financial secrets; all money amounts and aggregates are masked (ส่วนที่เป็นมติทีมยังรอยืนยัน owner).

Stock design prerequisite for Phase 2: one StockMovement ledger with source type/id, reversible/update-safe movements, explicit count adjustment, canonical unit conversion, and product_id references from InputItem. InputCatalog must not become a second product master; legacy encrypted names require owner-key migration before linking.

Task expense is optional and collapsed by default; linked transaction/labor records are created only when the expense section is used. Do not collect worker names unless the business requires them; if collected, mask/encrypt under people-data rule.

Clarify weather semantics: ForecastSnapshot stores issued forecasts; WeatherLog from past Open-Meteo forecast API is not farm sensor ground truth; sensor readings are the separate observed-input stream. Reconcile Insight and Recommendation before Phase 2.
```

## สิ่งที่ตรวจไม่ได้ / ข้อขัดแย้งที่ต้องยืนยัน

1. **`code_prototype` source/entry point:** ไม่อยู่ใน workspace root; PROJECT_STATUS บอกว่าแยกเก็บ แต่ตรวจจำนวน frontend ทั้ง workspace ที่อยู่นอก root ไม่ได้.
2. **Live scheduler, latest run, DB backup health, actual browser role:** ตรวจจาก source/API contract ได้ไม่ครบใน blueprint; ไม่มี endpoint สำหรับ job/backup status. ต้องให้ operator ยืนยัน runtime แยก.
3. **Snapshot/history semantics:** code มี `ForecastSnapshot`; UI/API read ไม่พบ. handoff ย้ำ WeatherLog ที่ดึง past days ไม่ใช่ sensor truth; อย่าใช้ WeatherLog เป็น ground truth.
4. **Owner confirmation:** ความลับของเมล็ด, รายละเอียดการเปิดเผยยอด stock ตาม D2/D3, และการ mask ตัวเลขการเงินทุกชนิดยังเป็นข้อเสนอ/สมมติฐานตาม prompt.
5. **Git cleanliness:** `git status` ใช้ไม่ได้เพราะ workspace นี้ไม่มี `.git`; ยืนยันได้เฉพาะว่าการทำงานนี้สร้างไฟล์ใหม่ตามที่ตั้งใจ 2 ไฟล์ ไม่สามารถพิสูจน์ diff ของ repository ได้.
6. **Framework version discrepancy:** `PROJECT_STATUS.md` ระบุ React 18 แต่ [package.json](package.json) ปัจจุบันระบุ React `^19.3.0`; ควรแก้เอกสารในรอบที่ได้รับอนุญาต.
