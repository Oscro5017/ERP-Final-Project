import { useEffect, useState } from 'react';
import { CalendarDays, CloudRain, Droplets, RefreshCw, RotateCcw, Thermometer } from 'lucide-react';
import WeatherWidget from '../../components/WeatherWidget';
import ThaiDateInput from '../../components/ThaiDateInput';
import Toast from '../../components/Toast';
import { api } from '../../lib/api';
import { formatThaiDate } from '../../utils/dateUtils';

function Weather() {
  const [fromDate, setFromDate] = useState('');
  const [toDate, setToDate] = useState('');
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [toastMessage, setToastMessage] = useState('');
  const [toastVisible, setToastVisible] = useState(false);

  const showToast = (message) => {
    setToastMessage(message);
    setToastVisible(true);
    setTimeout(() => setToastVisible(false), 3000);
  };

  const loadHistory = async (startDate = fromDate, endDate = toDate) => {
    try {
      setLoading(true);
      setError('');
      const params = new URLSearchParams();
      if (startDate) params.set('from', startDate);
      if (endDate) params.set('to', endDate);
      const query = params.toString();
      const data = await api(`/weather/history${query ? `?${query}` : ''}`);
      setLogs(data);
      return data;
    } catch (err) {
      setError(err.message || 'ไม่สามารถโหลดประวัติสภาพอากาศได้');
      return null;
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadHistory();
  }, []);

  const invalidDateRange = Boolean(fromDate && toDate && fromDate > toDate);

  const handleSearch = (event) => {
    event.preventDefault();
    if (!invalidDateRange) loadHistory(fromDate, toDate);
  };

  const handleClearFilters = async () => {
    setFromDate('');
    setToDate('');
    await loadHistory('', '');
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-slate-800">สภาพอากาศ</h1>
        <p className="text-sm text-slate-500">สภาพอากาศประจำวัน พยากรณ์ล่วงหน้า และบันทึกสภาพอากาศย้อนหลังของฟาร์ม</p>
      </div>

      <div id="forecast">
        <WeatherWidget
          onToast={showToast}
          onSyncSuccess={() => loadHistory()}
        />
      </div>

      <section id="history" className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-soft">
        <div className="flex flex-col gap-3 border-b border-slate-100 p-5 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 className="text-lg font-semibold text-slate-800">บันทึกสภาพอากาศย้อนหลัง</h2>
            <p className="text-sm text-slate-500">ข้อมูลจริงที่บันทึกไว้ แยกตามวัน</p>
          </div>
          <button
            type="button"
            onClick={() => loadHistory()}
            disabled={loading}
            className="inline-flex items-center justify-center gap-2 rounded-xl border border-slate-200 px-3 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-50 disabled:opacity-50"
          >
            <RefreshCw size={15} className={loading ? 'animate-spin' : ''} />
            รีเฟรชประวัติ
          </button>
        </div>

        <form onSubmit={handleSearch} className="flex flex-col gap-3 border-b border-slate-100 bg-slate-50/70 p-5 sm:flex-row sm:items-end">
          <label className="flex flex-1 flex-col gap-1 text-sm font-medium text-slate-700">
            ตั้งแต่วันที่
            <ThaiDateInput
              value={fromDate}
              onChange={setFromDate}
              label="วันที่เริ่มต้น"
            />
          </label>
          <label className="flex flex-1 flex-col gap-1 text-sm font-medium text-slate-700">
            ถึงวันที่
            <ThaiDateInput
              value={toDate}
              onChange={setToDate}
              label="วันที่สิ้นสุด"
            />
          </label>
          <button
            type="submit"
            disabled={loading || invalidDateRange}
            className="rounded-xl bg-farm-700 px-5 py-2 text-sm font-medium text-white transition hover:bg-farm-800 disabled:cursor-not-allowed disabled:opacity-50"
          >
            ค้นหาประวัติ
          </button>
          <button
            type="button"
            onClick={handleClearFilters}
            disabled={loading}
            className="inline-flex items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <RotateCcw size={15} />
            ล้างตัวกรอง
          </button>
          {invalidDateRange && <p className="text-sm text-rose-600 sm:basis-full">วันที่เริ่มต้นต้องไม่อยู่หลังวันที่สิ้นสุด</p>}
        </form>

        {error ? (
          <div className="m-5 rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700" role="alert">
            <p className="font-semibold">โหลดประวัติไม่สำเร็จ</p>
            <p>{error}</p>
          </div>
        ) : loading ? (
          <div className="p-10 text-center text-sm text-slate-500">กำลังโหลดบันทึกสภาพอากาศ...</div>
        ) : logs.length === 0 ? (
          <div className="p-10 text-center">
            <CalendarDays className="mx-auto mb-2 text-slate-400" size={24} />
            <p className="font-medium text-slate-700">ไม่พบข้อมูลในช่วงวันที่เลือก</p>
            <p className="mt-1 text-sm text-slate-500">ลองเลือกช่วงวันที่อื่น หรือรอให้ระบบบันทึกข้อมูลสภาพอากาศ</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] text-left text-sm">
              <thead className="bg-white text-xs uppercase text-slate-500">
                <tr>
                  <th scope="col" className="px-5 py-3 font-semibold">วันที่</th>
                  <th scope="col" className="px-5 py-3 font-semibold">สภาพอากาศ</th>
                  <th scope="col" className="px-5 py-3 font-semibold">อุณหภูมิ</th>
                  <th scope="col" className="px-5 py-3 font-semibold">ความชื้น</th>
                  <th scope="col" className="px-5 py-3 font-semibold">ปริมาณฝน</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {logs.map((log) => (
                  <tr key={log.id} className="text-slate-700 hover:bg-slate-50">
                    <td className="whitespace-nowrap px-5 py-4 font-medium">{formatThaiDate(log.log_date)}</td>
                    <td className="px-5 py-4">{log.condition}</td>
                    <td className="whitespace-nowrap px-5 py-4">
                      <span className="inline-flex items-center gap-1">
                        <Thermometer size={15} className="text-amber-500" />
                        {log.temp_min}–{log.temp_max} °C
                      </span>
                    </td>
                    <td className="whitespace-nowrap px-5 py-4">
                      <span className="inline-flex items-center gap-1">
                        <Droplets size={15} className="text-sky-500" />
                        {log.humidity}%
                      </span>
                    </td>
                    <td className="whitespace-nowrap px-5 py-4">
                      <span className="inline-flex items-center gap-1">
                        <CloudRain size={15} className="text-blue-500" />
                        {log.rainfall} มม.
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <Toast message={toastMessage} visible={toastVisible} />
    </div>
  );
}

export default Weather;
