import { Search, Plus, Filter } from 'lucide-react';
import { inventoryData } from '../data/mockData';
import StatusBadge from '../components/StatusBadge';

function Inventory() {
  const columns = ['รหัสสินค้า', 'ชื่อสินค้า', 'ประเภท', 'หน่วยนับ', 'คงเหลือ', 'ขั้นต่ำ', 'สถานะ'];

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-slate-800">คลังสินค้า</h1>
          <p className="text-sm text-slate-500">ติดตามสินค้าทั้งวัตถุดิบและผลผลิต</p>
        </div>
        <button className="inline-flex items-center gap-2 rounded-xl bg-farm-700 px-4 py-2.5 text-sm font-semibold text-white shadow-soft">
          <Plus size={16} />
          เพิ่มสินค้า
        </button>
      </div>

      <div className="flex flex-col gap-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-soft md:flex-row md:items-center md:justify-between">
        <div className="flex flex-1 items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2">
          <Search size={16} className="text-slate-400" />
          <input className="w-full bg-transparent text-sm outline-none" placeholder="ค้นหาสินค้า" />
        </div>
        <button className="flex items-center justify-center gap-2 rounded-xl border border-slate-200 px-3 py-2 text-sm text-slate-600">
          <Filter size={16} />
          ตัวกรองประเภท
        </button>
      </div>

      <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-soft">
        <div className="flex gap-2 border-b border-slate-200 p-3">
          <button className="rounded-full bg-farm-700 px-3 py-1.5 text-sm font-semibold text-white">วัตถุดิบ</button>
          <button className="rounded-full bg-slate-100 px-3 py-1.5 text-sm text-slate-600">ผลผลิต</button>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead className="bg-slate-50 text-slate-600">
              <tr>
                {columns.map((column) => (
                  <th key={column} className="px-4 py-3 font-semibold">{column}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {inventoryData.map((item) => (
                <tr key={item.id} className="border-t border-slate-100">
                  <td className="px-4 py-3 text-slate-700">{item.id}</td>
                  <td className="px-4 py-3 text-slate-700">{item.name}</td>
                  <td className="px-4 py-3 text-slate-700">{item.type}</td>
                  <td className="px-4 py-3 text-slate-700">{item.unit}</td>
                  <td className="px-4 py-3 text-slate-700">{item.stock}</td>
                  <td className="px-4 py-3 text-slate-700">{item.minimum}</td>
                  <td className="px-4 py-3"><StatusBadge status={item.status} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

export default Inventory;
