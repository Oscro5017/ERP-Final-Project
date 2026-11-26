import { useState } from 'react';
import { useAutomation } from '../components/AutomationPrompt';
import { AUTOMATIONS } from '../utils/automation';

const modes = [['', 'ถามทุกครั้ง'], ['auto', 'ให้ระบบจัดการ'], ['manual', 'จัดการเอง']];

function Settings() {
  const { preferences, save } = useAutomation();
  const [message, setMessage] = useState('');

  const change = async (key, mode) => {
    try {
      await save(key, mode);
      setMessage('บันทึกการตั้งค่าแล้ว');
    } catch (error) {
      setMessage(error.message);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-slate-800">ตั้งค่า</h1>
        <p className="mt-1 text-sm text-slate-500">เลือกว่าเรื่องไหนให้ระบบจัดการ เรื่องไหนจัดการเอง ใช้เฉพาะบัญชีของคุณ</p>
      </div>
      {message && <p role="status" className="rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600">{message}</p>}
      <section className="divide-y divide-slate-100 rounded-2xl border border-slate-200 bg-white shadow-soft">
        {Object.entries(AUTOMATIONS).map(([key, info]) => (
          <div key={key} className="flex flex-col gap-3 p-4 lg:flex-row lg:items-center lg:justify-between">
            <div className="text-sm">
              <h2 className="font-semibold text-slate-800">{info.title}</h2>
              <p className="text-slate-500">ระบบจัดการ: {info.auto}</p>
              <p className="text-slate-500">จัดการเอง: {info.manual}</p>
            </div>
            <div role="group" aria-label={info.title} className="inline-flex shrink-0 gap-1 self-start rounded-xl bg-slate-100 p-1">
              {modes.map(([mode, label]) => {
                const isChosen = (preferences[key] || '') === mode;
                return <button key={mode} type="button" aria-pressed={isChosen} onClick={() => change(key, mode)} className={`rounded-lg px-3 py-1.5 text-xs font-medium ${isChosen ? 'bg-white text-farm-800 shadow-sm' : 'text-slate-500'}`}>{label}</button>;
              })}
            </div>
          </div>
        ))}
      </section>
    </div>
  );
}

export default Settings;
