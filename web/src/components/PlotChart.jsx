import { useEffect, useState } from 'react';
import DoughnutChart from './charts/DoughnutChart';
import { api } from '../lib/api';
import { cropCycleStatuses } from '../constants/cropCycleStatus';

const statusColors = ['#2f7d4f', '#69a77a', '#d2a84a', '#4b8492', '#a8b5ab'];

function PlotChart() {
  const [cycles, setCycles] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');

  const loadCycles = async () => {
    setIsLoading(true);
    setError('');
    try {
      setCycles(await api('/crop-cycles'));
    } catch (requestError) {
      setError(requestError.message || 'โหลดสถานะรอบปลูกไม่สำเร็จ');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadCycles();
  }, []);

  const counts = cropCycleStatuses.map((status) => ({
    ...status,
    count: cycles.filter((cycle) => cycle.status === status.value).length,
  }));
  const chartData = {
    labels: counts.map((item) => item.label),
    datasets: [{
      data: counts.map((item) => item.count),
      backgroundColor: statusColors,
      borderWidth: 0,
      spacing: 3,
    }],
  };

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-soft">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold text-slate-800">รอบปลูกตามสถานะ</h3>
          <p className="text-sm text-slate-500">ข้อมูลปัจจุบันจากรอบปลูกทั้งหมด</p>
        </div>
      </div>
      {isLoading ? (
        <p className="py-16 text-center text-sm text-slate-500">กำลังโหลดสถานะรอบปลูก…</p>
      ) : error ? (
        <div className="py-10 text-center">
          <p role="alert" className="text-sm text-rose-600">{error}</p>
          <button onClick={loadCycles} className="mt-3 rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-700">ลองอีกครั้ง</button>
        </div>
      ) : cycles.length === 0 ? (
        <p className="py-16 text-center text-sm text-slate-500">ยังไม่มีข้อมูลรอบปลูก</p>
      ) : (
        <div className="grid items-center gap-4 sm:grid-cols-[minmax(0,1fr)_minmax(150px,0.9fr)]">
          <div className="mx-auto h-52 w-full max-w-[260px]">
            <DoughnutChart data={chartData} options={{ plugins: { legend: { display: false } } }} />
          </div>
          <ul className="space-y-2" aria-label="จำนวนรอบปลูกตามสถานะ">
            {counts.map((item, index) => (
              <li key={item.value} className="flex items-center justify-between gap-3 text-sm">
                <span className="flex min-w-0 items-center gap-2 text-slate-600">
                  <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ backgroundColor: statusColors[index] }} />
                  <span className="truncate">{item.label}</span>
                </span>
                <span className="font-semibold tabular-nums text-slate-800">{item.count}</span>
              </li>
            ))}
            <li className="border-t border-slate-100 pt-2 text-sm font-semibold text-slate-800">
              ทั้งหมด <span className="float-right tabular-nums">{cycles.length}</span>
            </li>
          </ul>
        </div>
      )}
    </div>
  );
}

export default PlotChart;
