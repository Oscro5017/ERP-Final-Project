import { revenueData } from '../data/mockData';
import LineChart from './charts/LineChart';

const chartData = {
  labels: revenueData.map((entry) => entry.day),
  datasets: [
    {
      label: 'รายรับ',
      data: revenueData.map((entry) => entry.income),
      borderColor: '#2f7d4f',
      backgroundColor: '#2f7d4f',
      borderWidth: 3,
      pointRadius: 4,
      pointHoverRadius: 6,
      tension: 0.35,
    },
    {
      label: 'รายจ่าย',
      data: revenueData.map((entry) => entry.expense),
      borderColor: '#94a3b8',
      backgroundColor: '#94a3b8',
      borderWidth: 3,
      pointRadius: 4,
      pointHoverRadius: 6,
      tension: 0.35,
    },
  ],
};

function RevenueChart() {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-soft">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold text-slate-800">รายรับ - รายจ่าย</h3>
          <p className="text-sm text-slate-500">แนวโน้มรายรับและรายจ่ายในเดือนนี้</p>
        </div>
      </div>
      <div className="h-72">
        <LineChart data={chartData} />
      </div>
    </div>
  );
}

export default RevenueChart;
