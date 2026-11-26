function StatusBadge({ status }) {
  const styles = {
    อนุบาล: 'bg-sky-100 text-sky-700',
    'สร้างพุ่ม': 'bg-emerald-100 text-emerald-700',
    'พร้อมเก็บเกี่ยว': 'bg-amber-100 text-amber-700',
    'เก็บเกี่ยวแล้ว': 'bg-yellow-100 text-yellow-700',
    ว่าง: 'bg-slate-100 text-slate-700',
    'กำลังปลูก': 'bg-emerald-100 text-emerald-700',
    'เก็บเกี่ยว': 'bg-amber-100 text-amber-700',
    'พักแปลง': 'bg-orange-100 text-orange-700',
    'ใกล้หมด': 'bg-rose-100 text-rose-700',
    'ปกติ': 'bg-emerald-100 text-emerald-700',
    'พร้อมจำหน่าย': 'bg-green-100 text-green-700',
    'กำลังส่ง': 'bg-sky-100 text-sky-700',
  };

  return <span className={`rounded-full px-3 py-1 text-xs font-semibold ${styles[status] || 'bg-slate-100 text-slate-700'}`}>{status}</span>;
}

export default StatusBadge;
