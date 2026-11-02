import { costData } from '../data/mockData';

function Costs() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-slate-800">ต้นทุนและกำไร</h1>
        <p className="text-sm text-slate-500">สรุปค่าใช้จ่ายและผลกำไรของกิจกรรมต่าง ๆ</p>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        {costData.map((item) => (
          <div key={item.label} className="rounded-2xl border border-slate-200 bg-white p-5 shadow-soft">
            <p className="text-sm text-slate-500">{item.label}</p>
            <p className="mt-2 text-xl font-semibold text-slate-800">{item.value}</p>
          </div>
        ))}
      </div>

      <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-soft">
        <p className="text-slate-600">ค่าใช้จ่ายหลักในเดือนนี้ ได้แก่ ปุ๋ยและเมล็ดพันธุ์ 12,500 บาท, ค่าแรงงาน 9,200 บาท และพลังงาน 8,510 บาท</p>
      </div>
    </div>
  );
}

export default Costs;
