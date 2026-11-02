import { useState, useEffect } from 'react';
import {
  Sun,
  CloudSun,
  Cloud,
  CloudRain,
  CloudLightning,
  Droplets,
  CloudDrizzle,
  RotateCw,
  MapPin,
  Calendar,
  Thermometer,
  ShieldCheck,
} from 'lucide-react';
import { api } from '../lib/api';
import { formatThaiWeekdayDate } from '../utils/dateUtils';
import LineChart from './charts/LineChart';

function getWeatherIcon(code, size = 20) {
  if (code === 0) return <Sun size={size} className="text-amber-500" />;
  if (code >= 1 && code <= 3) return <CloudSun size={size} className="text-amber-400" />;
  if (code >= 45 && code <= 48) return <Cloud size={size} className="text-slate-400" />;
  if (code >= 51 && code <= 57) return <CloudDrizzle size={size} className="text-sky-500" />;
  if (code >= 61 && code <= 67) return <CloudRain size={size} className="text-blue-500" />;
  if (code >= 80 && code <= 82) return <CloudRain size={size} className="text-blue-600" />;
  if (code >= 95) return <CloudLightning size={size} className="text-purple-600" />;
  return <Cloud size={size} className="text-slate-400" />;
}

export default function WeatherWidget({ onToast, onSyncSuccess, compact = false }) {
  const [forecast, setForecast] = useState([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState('');

  const loadForecast = async () => {
    try {
      setLoading(true);
      setError('');
      const data = await api('/weather/forecast?days=7');
      setForecast(data);
    } catch (err) {
      setError(err.message || 'ไม่สามารถโหลดข้อมูลพยากรณ์อากาศได้');
      if (onToast) onToast(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleSyncYesterday = async () => {
    try {
      setSyncing(true);
      const res = await api('/weather/sync-yesterday', { method: 'POST' });
      if (onToast) onToast(res.message || 'บันทึกข้อมูลเมื่อวานสำเร็จ');
      if (onSyncSuccess) await onSyncSuccess();
    } catch (err) {
      if (onToast) onToast(err.message);
    } finally {
      setSyncing(false);
    }
  };

  useEffect(() => {
    loadForecast();
  }, []);

  const todayForecast = forecast.length > 0 ? forecast[0] : null;
  const upcomingDays = forecast.length > 1 ? forecast.slice(1) : [];
  const temperatureChartData = {
    labels: forecast.map((day) => formatThaiWeekdayDate(day.date)),
    datasets: [
      {
        label: 'สูงสุด',
        data: forecast.map((day) => day.temp_max),
        borderColor: '#c27b25',
        backgroundColor: '#c27b25',
        pointRadius: 2,
        tension: 0.3,
      },
      {
        label: 'ต่ำสุด',
        data: forecast.map((day) => day.temp_min),
        borderColor: '#397b8a',
        backgroundColor: '#397b8a',
        pointRadius: 2,
        tension: 0.3,
      },
    ],
  };

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-soft">
      <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="text-lg font-semibold text-slate-800">{compact ? 'สภาพอากาศวันนี้' : 'พยากรณ์สภาพอากาศฟาร์ม (ละเอียด)'}</h3>
            <span className="inline-flex items-center gap-1 rounded-full bg-sky-50 px-2 py-0.5 text-xs font-medium text-sky-700">
              <MapPin size={11} />
              ดอยสะเก็ด, เชียงใหม่
            </span>
          </div>
          <p className="text-sm text-slate-500">อุณหภูมิ ความชื้น และฝนจากพยากรณ์ 7 วัน</p>
        </div>

        <div className="flex items-center gap-2">
          {!compact && <button
            onClick={handleSyncYesterday}
            disabled={syncing}
            className="inline-flex items-center gap-1 rounded-xl border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs font-medium text-slate-700 transition hover:bg-slate-100 disabled:opacity-50"
            title="ซิงก์ข้อมูลอากาศเมื่อวานลงประวัติฟาร์ม"
          >
            <ShieldCheck size={14} className="text-emerald-600" />
            {syncing ? 'กำลังซิงก์...' : 'ซิงก์เมื่อวาน'}
          </button>}
          <button
            onClick={loadForecast}
            disabled={loading}
            className="inline-flex items-center gap-1 rounded-xl bg-slate-100 px-3 py-1.5 text-xs font-medium text-slate-700 transition hover:bg-slate-200 disabled:opacity-50"
          >
            <RotateCw size={13} className={loading ? 'animate-spin' : ''} />
            รีเฟรช
          </button>
        </div>
      </div>

      {loading && forecast.length === 0 ? (
        <div className="py-12 text-center text-sm text-slate-400">กำลังดึงข้อมูลพยากรณ์อากาศจาก Open-Meteo...</div>
      ) : error ? (
        <div className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
          <p className="font-semibold">เกิดข้อผิดพลาดในการโหลดสภาพอากาศ</p>
          <p className="text-xs text-rose-600">{error}</p>
          <button
            onClick={loadForecast}
            className="mt-2 rounded-lg bg-rose-600 px-3 py-1 text-xs font-medium text-white hover:bg-rose-700"
          >
            ลองใหม่อีกครั้ง
          </button>
        </div>
      ) : (
        <div className="space-y-4">
          {/* Today Highlight Card */}
          {todayForecast && (
            <div className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-sky-500 via-sky-600 to-indigo-700 p-5 text-white shadow-md">
              <div className="flex flex-col justify-between gap-4 md:flex-row md:items-center">
                <div className="flex items-center gap-4">
                  <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-white/20 backdrop-blur-md">
                    {getWeatherIcon(todayForecast.weather_code, 36)}
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="rounded-full bg-white/25 px-2.5 py-0.5 text-xs font-semibold backdrop-blur-sm">
                        วันนี้ ({formatThaiWeekdayDate(todayForecast.date)})
                      </span>
                      <span className="text-xs text-sky-100">{todayForecast.condition}</span>
                    </div>
                    <div className="mt-1 flex items-baseline gap-2">
                      <span className="text-3xl font-bold tracking-tight">
                        {todayForecast.temp_max}°C
                      </span>
                      <span className="text-sm text-sky-200">
                        ต่ำสุด {todayForecast.temp_min}°C
                      </span>
                    </div>
                  </div>
                </div>

                <div className="grid grid-cols-3 gap-3 rounded-xl bg-white/10 p-3 backdrop-blur-md">
                  <div className="text-center">
                    <div className="flex items-center justify-center gap-1 text-sky-200">
                      <Thermometer size={14} />
                      <span className="text-xs">อุณหภูมิ</span>
                    </div>
                    <p className="mt-0.5 text-sm font-bold">
                      {todayForecast.temp_min} - {todayForecast.temp_max}°
                    </p>
                  </div>
                  <div className="border-x border-white/20 px-2 text-center">
                    <div className="flex items-center justify-center gap-1 text-sky-200">
                      <Droplets size={14} />
                      <span className="text-xs">ความชื้น</span>
                    </div>
                    <p className="mt-0.5 text-sm font-bold">{todayForecast.humidity}%</p>
                  </div>
                  <div className="text-center">
                    <div className="flex items-center justify-center gap-1 text-sky-200">
                      <CloudRain size={14} />
                      <span className="text-xs">ปริมาณฝน</span>
                    </div>
                    <p className="mt-0.5 text-sm font-bold">{todayForecast.rainfall} มม.</p>
                  </div>
                </div>
              </div>
            </div>
          )}

          {forecast.length > 0 && (
            <section className="rounded-xl border border-slate-200 p-4" aria-label="กราฟอุณหภูมิพยากรณ์ 7 วัน">
              <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
                <h4 className="text-sm font-semibold text-slate-800">แนวโน้มอุณหภูมิ 7 วัน</h4>
                <span className="text-xs text-slate-500">พยากรณ์จาก Open-Meteo ไม่ใช่ข้อมูลเซนเซอร์</span>
              </div>
              <div className={compact ? 'h-36 sm:h-40' : 'h-44 sm:h-52'}>
                <LineChart
                  data={temperatureChartData}
                  beginAtZero={false}
                  options={{ plugins: { legend: { display: true, position: 'bottom' } } }}
                />
              </div>
            </section>
          )}

          {/* 6-Day Forward Forecast Grid */}
          {!compact && <div>
            <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500">
              พยากรณ์ล่วงหน้าอีก 6 วัน
            </p>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
              {upcomingDays.map((day) => {
                const isRainy = day.rainfall > 2.0 || day.condition.includes('ฝน');

                return (
                  <div
                    key={day.date}
                    className={`flex flex-col justify-between rounded-xl border p-3 transition ${
                      isRainy
                        ? 'border-blue-200 bg-blue-50/50 hover:bg-blue-50'
                        : 'border-slate-200 bg-slate-50 hover:bg-slate-100/70'
                    }`}
                  >
                    <div>
                      <p className="text-xs font-semibold text-slate-700">
                        {formatThaiWeekdayDate(day.date)}
                      </p>
                      <div className="my-2 flex items-center justify-center">
                        {getWeatherIcon(day.weather_code, 26)}
                      </div>
                      <p className="line-clamp-1 text-center text-[11px] font-medium text-slate-600" title={day.condition}>
                        {day.condition}
                      </p>
                    </div>

                    <div className="mt-2 border-t border-slate-200/60 pt-2 space-y-1 text-xs">
                      <div className="flex items-center justify-between text-slate-800 font-semibold">
                        <span className="text-amber-600">{day.temp_max}°</span>
                        <span className="text-slate-400">/</span>
                        <span className="text-blue-600">{day.temp_min}°</span>
                      </div>
                      <div className="flex items-center justify-between text-[11px] text-slate-500">
                        <span className="flex items-center gap-0.5">
                          <Droplets size={10} className="text-sky-500" />
                          {day.humidity}%
                        </span>
                        <span className="flex items-center gap-0.5">
                          <CloudRain size={10} className="text-blue-500" />
                          {day.rainfall} มม.
                        </span>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>}
        </div>
      )}
    </div>
  );
}
