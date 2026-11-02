import { Plus } from 'lucide-react';
import { salesData } from '../data/mockData';

function Sales() {
  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-slate-800">การขาย</h1>
          <p className="text-sm text-slate-500">ตรวจสอบรายการขายและยอดขายของฟาร์ม</p>
        </div>
        <button className="inline-flex items-center gap-2 rounded-xl bg-farm-700 px-4 py-2.5 text-sm font-semibold text-white shadow-soft">
          <Plus size={16} />
          สร้างรายการขาย
        </button>
      </div>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {[
          ['ยอดขายวันนี้', '3,250 บาท'],
          ['ยอดขายสัปดาห์นี้', '12,840 บาท'],
          ['ยอดขายเดือนนี้', '48,750 บาท'],
          ['ยอดขายปีนี้', '286,950 บาท'],
        ].map(([label, value]) => (
          <div key={label} className="rounded-2xl border border-slate-200 bg-white p-5 shadow-soft">
            <p className="text-sm text-slate-500">{label}</p>
            <p className="mt-2 text-xl font-semibold text-slate-800">{value}</p>
          </div>
        ))}
      </div>

      <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-soft">
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead className="bg-slate-50 text-slate-600">
              <tr>
                <th className="px-4 py-3">วันที่</th>
                <th className="px-4 py-3">เลขที่บิล</th>
                <th className="px-4 py-3">ลูกค้า</th>
                <th className="px-4 py-3">รายการ</th>
                <th className="px-4 py-3">จำนวน</th>
                <th className="px-4 py-3">ยอดรวม</th>
              </tr>
            </thead>
            <tbody>
              {salesData.map((item) => (
                <tr key={item.bill} className="border-t border-slate-100">
                  <td className="px-4 py-3 text-slate-700">{item.date}</td>
                  <td className="px-4 py-3 text-slate-700">{item.bill}</td>
                  <td className="px-4 py-3 text-slate-700">{item.customer}</td>
                  <td className="px-4 py-3 text-slate-700">{item.item}</td>
                  <td className="px-4 py-3 text-slate-700">{item.amount}</td>
                  <td className="px-4 py-3 text-slate-700">{item.total}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

export default Sales;
