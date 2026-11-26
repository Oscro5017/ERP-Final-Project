import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../lib/api';
import StatCard from '../components/StatCard';
import { Package, CheckSquare, AlertTriangle, Wallet } from 'lucide-react';
import PlotChart from '../components/PlotChart';
import TaskWidget from '../components/TaskWidget';
import WeatherWidget from '../components/WeatherWidget';
import Toast from '../components/Toast';
import { formatMoney } from '../utils/format';
import { MASKED_NUMBER, readAmount } from '../utils/masking';

function Dashboard() {
  const [summary, setSummary] = useState(null);
  const [freshness, setFreshness] = useState(null);
  const [toastMessage, setToastMessage] = useState('');
  const [toastVisible, setToastVisible] = useState(false);

  const showToast = (message) => {
    setToastMessage(message);
    setToastVisible(true);
    setTimeout(() => setToastVisible(false), 3000);
  };

  useEffect(() => {
    let active = true;
    api('/dashboard/summary')
      .then((data) => {
        if (active) setSummary(data);
      })
      .catch(() => {});
    api('/freshness/lots')
      .then((data) => {
        if (active) setFreshness(data);
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, []);

  const profit = readAmount(summary?.finance_month?.profit);
  const formattedProfit = !summary
    ? '—'
    : profit.isMasked ? MASKED_NUMBER : (profit.value === null ? '—' : formatMoney(profit.value));

  const tasksOverdue = summary?.tasks_overdue ?? 0;

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 border-b border-[#e4e9e1] pb-5 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="mb-1 text-xs font-semibold uppercase tracking-[0.14em] text-farm-700">FARM OVERVIEW</p>
          <h1 className="text-2xl font-semibold tracking-tight text-slate-900 sm:text-[28px]">ภาพรวมฟาร์ม</h1>
          <p className="mt-1 text-sm text-slate-600">ดูรอบปลูก งานใกล้ถึงกำหนด และพยากรณ์อากาศ</p>
        </div>
      </div>

      {freshness && (freshness.expired > 0 || freshness.expiring > 0) && (
        <Link to="/warehouse/fresh" className="flex items-center gap-2 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm font-medium text-amber-800">
          <AlertTriangle size={16} /> ของสดหมดอายุ {freshness.expired} ล็อต · ใกล้หมดอายุ {freshness.expiring} ล็อต
        </Link>
      )}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          title="รายการในคลัง"
          value={summary?.product_count ?? '—'}
          icon={Package}
          tone="green"
        />
        <StatCard
          title="งานวันนี้"
          value={summary?.tasks_due_today ?? '—'}
          icon={CheckSquare}
          tone="blue"
        />
        <StatCard
          title="งานเลยกำหนด"
          value={summary?.tasks_overdue ?? '—'}
          icon={AlertTriangle}
          tone={tasksOverdue > 0 ? 'red' : 'yellow'}
        />
        <StatCard
          title="กำไรเดือนนี้"
          value={formattedProfit}
          icon={Wallet}
          tone="green"
        />
      </div>

      <div className="grid items-start gap-6 xl:grid-cols-2">
        <PlotChart />
        <WeatherWidget compact onToast={showToast} />
      </div>

      <TaskWidget onToast={showToast} />
      <Toast message={toastMessage} visible={toastVisible} />
    </div>
  );
}

export default Dashboard;
