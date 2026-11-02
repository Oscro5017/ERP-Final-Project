# Context handoff — ERP ฟาร์ม (SE01): Pi 5 เก็บข้อมูลอากาศ — 31 ต.ค. 2026

> ใช้ไฟล์นี้เป็นบริบทสำหรับแชทถัดไป ไม่ใช่คำสั่งให้แก้โค้ดทั้งหมดทันที อ่าน `PROJECT_CONTEXT.md`, `PROJECT_STATUS.md` และ prompt ใน `Project-Phase/` ก่อนทำงานต่อถ้าจำเป็น

## วิธีทำงานกับผู้ใช้

- ตอบภาษาไทย ตรงไปตรงมา และแยกสิ่งที่ยืนยันแล้วออกจากสิ่งที่ยังเป็นข้อสันนิษฐาน
- ห้ามขอให้ผู้ใช้ส่งค่า secret มาในแชท เช่น `ENCRYPTION_KEY`, `JWT_SECRET`, `DEVICE_TOKEN`, รหัสผ่าน Wi-Fi หรือรหัสผ่านระบบ
- สำหรับงานโค้ด ผู้ใช้ต้องการ prompt spec เป็นไฟล์ `.md` ใน `Project-Phase/` ให้ coding agent ทำงาน; งานที่ต้องทำเองบน Pi/Windows/เราเตอร์ให้แยกเป็นขั้นตอนชัดเจน
- อย่าถือว่าการเห็น HTTP `200` เพียงอย่างเดียวยืนยันข้อมูลในฐานข้อมูลแล้ว ให้ตรวจฐานข้อมูลหรือ log ตามความเหมาะสม
- อย่าทดสอบหรือรัน test suite เว้นแต่ผู้ใช้ขอ

## เป้าหมายปัจจุบัน

ใช้ Raspberry Pi 5 ที่อาจารย์ให้ยืมเป็นเครื่องชั่วคราวเพื่อให้ backend เก็บข้อมูลสภาพอากาศจาก Open-Meteo ต่อเนื่องก่อน ยังไม่มีผู้ใช้ระบบจริง และยังไม่เปิด Cloudflare Tunnel เป้าหมายภายหลังยังเป็น Raspberry Pi 4 2GB

## สิ่งที่ทำเสร็จในแชทนี้

- ลง Raspberry Pi OS Lite 64-bit; Pi รายงาน `aarch64`, timezone `Asia/Bangkok`, NTP ทำงาน
- Pi ต่อเราเตอร์ 3BB ด้วยสาย Ethernet; คอม Windows ต่อ Wi-Fi บ้านเราเตอร์เดียวกัน จึง SSH ถึง Pi ได้ อินเทอร์เน็ตบ้านที่เคยขัดข้องผู้ใช้แจ้งว่าแก้แล้ว
- ส่ง `app/`, `frontend/`, `requirements.txt` จาก Windows ไป `~/erp-app` ด้วย `scp`
  - การส่งครั้งแรกมี `__pycache__` ติดไปด้วย; เคยให้คำสั่งลบ cache แต่ผู้ใช้ยังไม่ได้ยืนยันชัดเจนว่ารันแล้ว
- สร้าง Python virtual environment และติดตั้ง dependencies สำเร็จ; ผล `pip install -r requirements.txt` แสดงว่ารายการที่กำหนดติดตั้งครบแล้ว บน Python 3.13
- สร้าง `~/erp-app/.env` บน Pi โดยสุ่ม key/token ในเครื่องโดยตรงและตั้ง permission `600`; ค่า secret ไม่ถูกแสดงในแชท
  - ยังไม่ได้ยืนยันว่าผู้ใช้สำรอง `ENCRYPTION_KEY` แยกจากฐานข้อมูลแล้ว
- สร้างและเปิดใช้งาน systemd service `organic-farm.service`
  - `enabled`, `active (running)` ยืนยัน ณ 31 ต.ค. 2026 เวลา 14:05 น. เวลาไทย
  - รัน `uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1`, `Restart=always`
  - bind ที่ `127.0.0.1` จึงเข้าจากเครื่องอื่นใน LAN โดยตรงไม่ได้; ยังไม่มี Tunnel
- เปิดหน้า frontend จากคอมผ่าน SSH local port forwarding:
  - Windows PowerShell: `ssh -N -L 8000:127.0.0.1:8000 pi@pi.local`
  - Browser: `http://127.0.0.1:8000`
- Log แสดง `GET /`, assets, `POST /auth/login`, `GET /weather/forecast` และ `POST /weather/sync-yesterday` ตอบ `200 OK`; `favicon.ico` ตอบ 404 ซึ่งไม่กระทบหน้าเว็บ
- การทดสอบ frontend ทำให้มี `PATCH /crop-cycles/1` และ `/crop-cycles/7` สำเร็จ ข้อมูลดังกล่าวเป็นแถว seed/demo ในฐานข้อมูลใหม่ ไม่ใช่ข้อมูลจริงของฟาร์ม
- ผู้ใช้เปิด SQLite CLI แล้วเห็น `weather_logs` วันที่ 22–30 ต.ค. 2026 รวม 9 แถวในผล `LIMIT 10`; ค่า `fetched_at` แสดง 07:05–07:09 UTC (ประมาณ 14:05–14:09 เวลาไทย) วันที่ 31 ต.ค.

## ข้อเท็จจริงสำคัญเกี่ยวกับข้อมูลอากาศ

- ใน `app/services/weather.py` ทั้ง forecast และการดึงวันที่ผ่านมาใช้ `https://api.open-meteo.com/v1/forecast`
- `ForecastSnapshot` บันทึก forecast ที่ออกในแต่ละรอบ (ตั้งเวลาไว้ 08:05 น. เวลาไทย) แยกตาม `issued_date` และ `target_date`
- `WeatherLog` job เวลา 08:00 น. เรียก `sync_yesterday_weather()` เพื่อดึงค่าของเมื่อวาน; ตอน startup มี catch-up ตรวจย้อนหลัง 14 วันถึงเมื่อวาน
- **ห้ามเรียก WeatherLog ว่าค่าตรวจวัดจริงที่ฟาร์ม**: code ขอวันที่ผ่านมาโดยใช้ Forecast API; Open-Meteo อธิบายข้อมูล past days ของ Forecast API ว่าเป็น archived forecasts. เป็นค่าจาก API/แบบจำลอง ไม่ใช่เซนเซอร์หรือสถานีวัดในฟาร์ม
- Historical Weather API ใช้ reanalysis ซึ่งอาศัยแบบจำลองร่วมกับข้อมูลสังเกตการณ์ แต่ก็ไม่ใช่การวัดตรงจุดของฟาร์ม
- ดังนั้นการเปรียบเทียบ ForecastSnapshot กับ WeatherLog เป็นการเทียบกับค่า API/model-based สำหรับวันที่ผ่านมา ไม่ใช่ ground truth; ต้องมี sensor หรือสถานีตรวจวัดใกล้ฟาร์มเพื่อประเมินความแม่นยำจริง
- อ้างอิงเอกสาร Open-Meteo: [Forecast API](https://open-meteo.com/en/docs), [Historical Weather API](https://open-meteo.com/en/docs/historical-weather-api)

## สถานะที่ยังไม่ยืนยัน / งานถัดไป

1. ผู้ใช้ยังไม่ได้ส่งผล query `COUNT/MIN/MAX` ของ `weather_logs` และ `forecast_snapshots`; มีเพียงรายการ `weather_logs` 9 แถวจากคำสั่ง `LIMIT 10`
2. ยังไม่ได้ยืนยันว่ามี ForecastSnapshot ใน DB; service เริ่ม 31 ต.ค. เวลา 14:05 น. หลังเวลา schedule 08:05 ดังนั้นรอบ forecast ถัดไปควรเป็น 1 พ.ย. เวลา 08:05 หาก service ทำงานต่อ
3. ยังไม่ได้สังเกต scheduler ณ 08:00/08:05 จริง; ใช้ `journalctl -u organic-farm` และ query SQLite read-only เพื่อตรวจหลังรอบแรก
4. `journalctl` ที่ส่งมาก่อนหน้านี้ไม่แสดงข้อความ catch-up; แต่ DB มีข้อมูล 22–30 ต.ค. จึงควรตรวจจำนวนและช่วงวันที่จริง ไม่สรุปว่าครบ 14 วัน
5. ยังไม่ได้ตั้ง daily SQLite backup ไป flash drive/สื่อนอก Pi, ยังไม่ได้ตั้ง persistent/size-limited journald และยังไม่ได้ทดสอบ restore
6. ยังไม่ได้ตั้ง sensor; ขณะนี้เป็นข้อมูลจาก Open-Meteo เท่านั้น
7. ยังไม่มีการแก้โค้ดใน workspace ระหว่างช่วงตั้ง Pi นี้; ไฟล์บน Pi เป็นสำเนาจากโปรเจคที่ส่งขึ้นไปก่อนหน้านี้
8. มี workflow deploy แบบ manual ที่อธิบายแล้ว: build frontend บน Windows เมื่อแก้ UI, archive เฉพาะ `app frontend requirements.txt`, ส่งด้วย scp; บน Pi stop service, สำรอง DB ด้วย `sqlite3 .backup`, extract, ติดตั้ง requirements เฉพาะเมื่อเปลี่ยน แล้ว start และดู status/logs. **ไม่ส่ง** `.env`, `erp.db`, `.venv`, `node_modules` หรือ backup จากเครื่อง dev ไป Pi
9. หากผู้ใช้ต้องการทดสอบ Flutter/mobile app ให้ตรวจสถานะ Phase 4 ก่อน: handoff เดิมระบุว่า Flutter ยังไม่เริ่ม; อย่าสมมติว่ามี mobile app พร้อมใช้งาน

## คำสั่งตรวจ DB แบบอ่านอย่างเดียว

บน Pi:

```bash
cd ~/erp-app
sqlite3 -readonly erp.db
```

ใน `sqlite>`:

```sql
SELECT COUNT(*) AS rows, MIN(log_date) AS first_date, MAX(log_date) AS last_date FROM weather_logs;
SELECT log_date, temp_min, temp_max, humidity, rainfall, condition, fetched_at FROM weather_logs ORDER BY log_date DESC LIMIT 10;
SELECT COUNT(*) AS rows, MIN(issued_date) AS first_issue, MAX(issued_date) AS last_issue FROM forecast_snapshots;
SELECT issued_date, target_date, lead_days, temp_min, temp_max, precip_mm, source FROM forecast_snapshots ORDER BY issued_date DESC, target_date LIMIT 15;
```

## แนวทางเริ่มแชทต่อ

เริ่มจากสรุปว่า service บน Pi ทำงานแล้วและดูข้อมูลย้อนหลังได้ จากนั้นตรวจจำนวน WeatherLog/ForecastSnapshot และช่วยตั้ง backup ก่อนขยายการทำงานต่อ รักษาขอบเขต weather-only/local-only ตามเป้าหมายของผู้ใช้ และแยกข้อจำกัดของข้อมูล API ออกจากข้อมูลเซนเซอร์ให้ชัดเจน
