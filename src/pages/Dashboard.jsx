import { useState } from 'react';
import PlotChart from '../components/PlotChart';
import TaskWidget from '../components/TaskWidget';
import WeatherWidget from '../components/WeatherWidget';
import Toast from '../components/Toast';

function Dashboard() {
  const [toastMessage, setToastMessage] = useState('');
  const [toastVisible, setToastVisible] = useState(false);

  const showToast = (message) => {
    setToastMessage(message);
    setToastVisible(true);
    setTimeout(() => setToastVisible(false), 3000);
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-slate-800">ภาพรวมฟาร์ม</h1>
          <p className="text-sm text-slate-500">ดูรอบปลูก งานใกล้ถึงกำหนด และพยากรณ์อากาศ</p>
        </div>
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

