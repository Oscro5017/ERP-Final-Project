import { harvestData } from '../data/mockData';

function Harvest() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-slate-800">ผลผลิต</h1>
        <p className="text-sm text-slate-500">ติดตามผลผลิตที่เก็บเกี่ยวและพร้อมจำหน่าย</p>
      </div>

      <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-soft">
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead className="bg-slate-50 text-slate-600">
              <tr>
                <th className="px-4 py-3">รหัส</th>
                <th className="px-4 py-3">พืช</th>
                <th className="px-4 py-3">น้ำหนัก</th>
                <th className="px-4 py-3">แปลง</th>
                <th className="px-4 py-3">วันที่</th>
                <th className="px-4 py-3">ราคา</th>
                <th className="px-4 py-3">สถานะ</th>
              </tr>
            </thead>
            <tbody>
              {harvestData.map((item) => (
                <tr key={item.id} className="border-t border-slate-100">
                  <td className="px-4 py-3 text-slate-700">{item.id}</td>
                  <td className="px-4 py-3 text-slate-700">{item.crop}</td>
                  <td className="px-4 py-3 text-slate-700">{item.weight}</td>
                  <td className="px-4 py-3 text-slate-700">{item.plot}</td>
                  <td className="px-4 py-3 text-slate-700">{item.date}</td>
                  <td className="px-4 py-3 text-slate-700">{item.price}</td>
                  <td className="px-4 py-3 text-slate-700">{item.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

export default Harvest;
