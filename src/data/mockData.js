export const sidebarItems = [
  { name: 'หน้าภาพรวม', path: '/', icon: 'LayoutDashboard' },
  { name: 'สภาพอากาศ', path: '/weather', icon: 'CloudSun' },
  { name: 'แปลงเพาะปลูก', path: '/plots', icon: 'Sprout' },
  { name: 'กิจกรรมการเพาะปลูก', path: '/activities', icon: 'ClipboardList' },
  { name: 'ผลผลิต', path: '/harvest', icon: 'Leaf' },
  { name: 'คลังสินค้า', path: '/inventory', icon: 'Warehouse' },
  { name: 'การขาย', path: '/sales', icon: 'ShoppingCart' },
  { name: 'ต้นทุนและกำไร', path: '/costs', icon: 'Wallet' },
  { name: 'รายงาน', path: '/reports', icon: 'BarChart3' },
  { name: 'ผู้ใช้งาน', path: '/users', icon: 'Users' },
  { name: 'ตั้งค่า', path: '/settings', icon: 'Settings' },
];

export const plotData = [
  {
    id: 'A1',
    name: 'แปลง A1',
    crop: 'ผักกาดหอม',
    cycle: 'รอบที่ 3/2567',
    plantedDate: '10 พ.ค. 2567',
    status: 'กำลังปลูก',
    color: 'bg-green-600',
  },
  {
    id: 'A2',
    name: 'แปลง A2',
    crop: 'คะน้า',
    cycle: 'รอบที่ 2/2567',
    plantedDate: '5 พ.ค. 2567',
    status: 'กำลังปลูก',
    color: 'bg-green-600',
  },
  {
    id: 'B1',
    name: 'แปลง B1',
    crop: 'ผักบุ้ง',
    cycle: 'รอบที่ 4/2567',
    plantedDate: '12 พ.ค. 2567',
    status: 'กำลังปลูก',
    color: 'bg-green-600',
  },
  {
    id: 'B2',
    name: 'แปลง B2',
    crop: 'กวางตุ้ง',
    cycle: 'รอบที่ 3/2567',
    plantedDate: '8 พ.ค. 2567',
    status: 'เก็บเกี่ยว',
    color: 'bg-yellow-500',
  },
  {
    id: 'C1',
    name: 'แปลง C1',
    crop: 'ผักกาดขาว',
    cycle: 'รอบที่ 1/2567',
    plantedDate: '20 เม.ย. 2567',
    status: 'พักแปลง',
    color: 'bg-orange-500',
  },
];

export const inventoryData = [
  { id: 'SM001', name: 'เมล็ดพันธุ์ผักกาดหอม', type: 'เมล็ดพันธุ์', unit: 'กรัม', stock: 150, minimum: 200, status: 'ใกล้หมด' },
  { id: 'SM002', name: 'เมล็ดพันธุ์คะน้า', type: 'เมล็ดพันธุ์', unit: 'กรัม', stock: 350, minimum: 200, status: 'ปกติ' },
  { id: 'FT001', name: 'ปุ๋ยคอก', type: 'ปุ๋ย', unit: 'กก.', stock: 20, minimum: 30, status: 'ใกล้หมด' },
  { id: 'FT002', name: 'ปุ๋ยหมัก', type: 'ปุ๋ย', unit: 'กก.', stock: 45, minimum: 30, status: 'ปกติ' },
  { id: 'CH001', name: 'ไตรโคเดอร์มา', type: 'สารชีวภาพ', unit: 'ลิตร', stock: 2, minimum: 5, status: 'ใกล้หมด' },
];

export const salesData = [
  { date: '20 พ.ค. 67', bill: 'INV670520-001', customer: 'ร้านผักสีเขียว', item: 'ผักกาดหอม', amount: '20 กก.', total: '1,200 บาท' },
  { date: '20 พ.ค. 67', bill: 'INV670520-002', customer: 'ร้านสุขภาพดี', item: 'คะน้า', amount: '15 กก.', total: '600 บาท' },
  { date: '19 พ.ค. 67', bill: 'INV670519-001', customer: 'ตลาดสด', item: 'ผักบุ้ง', amount: '10 กก.', total: '300 บาท' },
];

export const activityData = [
  { date: '20 พ.ค. 67', activity: 'รดน้ำ', detail: 'รดน้ำช่วงเช้า', person: 'พนักงาน 1' },
  { date: '18 พ.ค. 67', activity: 'ใส่ปุ๋ย', detail: 'ปุ๋ยคอก 5 กก.', person: 'พนักงาน 2' },
  { date: '15 พ.ค. 67', activity: 'พ่นสารชีวภาพ', detail: 'ไตรโคเดอร์มา', person: 'พนักงาน 1' },
];

export const revenueData = [
  { day: '1', income: 18000, expense: 12500 },
  { day: '2', income: 22000, expense: 14000 },
  { day: '3', income: 24000, expense: 15000 },
  { day: '4', income: 21000, expense: 12000 },
  { day: '5', income: 26000, expense: 13500 },
  { day: '6', income: 28000, expense: 14500 },
  { day: '7', income: 30000, expense: 16000 },
];

export const latestHarvests = [
  { name: 'ผักกาดหอม', weight: '120 กก.', plot: 'แปลง A1', date: '20 พ.ค. 2567', status: 'พร้อมจำหน่าย' },
  { name: 'คะน้า', weight: '80 กก.', plot: 'แปลง A2', date: '18 พ.ค. 2567', status: 'เก็บเกี่ยวแล้ว' },
  { name: 'ผักบุ้ง', weight: '65 กก.', plot: 'แปลง B1', date: '16 พ.ค. 2567', status: 'กำลังส่ง' },
];

export const activityTimeline = [
  { date: '20 พ.ค. 67', plot: 'แปลง A1', title: 'รดน้ำ', detail: 'รดน้ำช่วงเช้า 2 รอบ', person: 'พนักงาน 1', status: 'สำเร็จ' },
  { date: '18 พ.ค. 67', plot: 'แปลง A2', title: 'ใส่ปุ๋ย', detail: 'ปุ๋ยคอก 5 กก. + ปุ๋ยหมัก 3 กก.', person: 'พนักงาน 2', status: 'สำเร็จ' },
  { date: '15 พ.ค. 67', plot: 'แปลง B1', title: 'พ่นสารชีวภาพ', detail: 'ไตรโคเดอร์มา 2 ลิตร', person: 'พนักงาน 3', status: 'รอตรวจ' },
  { date: '12 พ.ค. 67', plot: 'แปลง C1', title: 'เก็บเกี่ยว', detail: 'เก็บผักกาดขาว 40 กก.', person: 'พนักงาน 1', status: 'สำเร็จ' },
];

export const harvestData = [
  { id: 'HT001', crop: 'ผักกาดหอม', weight: '120 กก.', plot: 'แปลง A1', date: '20 พ.ค. 2567', price: '960 บาท', status: 'พร้อมจำหน่าย' },
  { id: 'HT002', crop: 'คะน้า', weight: '80 กก.', plot: 'แปลง A2', date: '18 พ.ค. 2567', price: '640 บาท', status: 'เก็บเกี่ยวแล้ว' },
  { id: 'HT003', crop: 'ผักบุ้ง', weight: '65 กก.', plot: 'แปลง B1', date: '16 พ.ค. 2567', price: '520 บาท', status: 'กำลังส่ง' },
];

export const costData = [
  { label: 'รายรับเดือนนี้', value: '48,750 บาท', tone: 'green' },
  { label: 'ค่าใช้จ่ายเดือนนี้', value: '30,210 บาท', tone: 'slate' },
  { label: 'กำไรสุทธิ', value: '18,540 บาท', tone: 'emerald' },
];

export const userData = [
  { name: 'กรกช บุญมี', role: 'เจ้าของฟาร์ม', shift: 'เช้า', status: 'ออนไลน์' },
  { name: 'นภัสวรรณ จันทร์ฉาย', role: 'พนักงานประจำแปลง', shift: 'เช้า', status: 'กำลังทำงาน' },
  { name: 'ฐิติมา พันธุ์แก้ว', role: 'ผู้จัดการคลัง', shift: 'บ่าย', status: 'ออนไลน์' },
];
