import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { Bot, PencilLine } from 'lucide-react';
import Modal from './Modal';
import { api } from '../lib/api';
import { AUTOMATIONS } from '../utils/automation';

const AutomationContext = createContext(null);

/**
 * Asks whether the system should handle something, remembering the answer when the user wants.
 * ask(key, detail) resolves to 'auto', 'manual', or null when the user closes the question.
 */
export function AutomationProvider({ children }) {
  const [preferences, setPreferences] = useState({});
  const [question, setQuestion] = useState(null);
  const [remember, setRemember] = useState(false);
  const [error, setError] = useState('');
  const loaded = useRef(null);
  const current = useRef({});

  const apply = useCallback((next) => {
    current.current = next;
    setPreferences(next);
  }, []);

  useEffect(() => {
    // Without saved choices the safe behaviour is to ask.
    loaded.current = api('/preferences/automation').then(apply).catch(() => {});
  }, [apply]);

  const save = useCallback(async (key, mode) => {
    if (mode) await api(`/preferences/automation/${key}`, { method: 'PUT', body: JSON.stringify({ mode }) });
    else await api(`/preferences/automation/${key}`, { method: 'DELETE' });
    const next = { ...current.current };
    if (mode) next[key] = mode;
    else delete next[key];
    apply(next);
  }, [apply]);

  const ask = useCallback(async (key, detail = '') => {
    await loaded.current;
    if (current.current[key]) return current.current[key];
    return new Promise((resolve) => {
      setRemember(false);
      setError('');
      setQuestion({ key, detail, resolve });
    });
  }, []);

  const answer = async (mode) => {
    if (mode && remember) {
      try {
        await save(question.key, mode);
      } catch (err) {
        setError(`จำตัวเลือกไม่สำเร็จ: ${err.message} (เอาเครื่องหมาย “ใช้เสมอ” ออกเพื่อทำต่อ)`);
        return;
      }
    }
    setQuestion(null);
    question.resolve(mode);
  };

  const value = useMemo(() => ({ ask, preferences, save }), [ask, preferences, save]);
  const info = question && AUTOMATIONS[question.key];

  return (
    <AutomationContext.Provider value={value}>
      {children}
      <Modal isOpen={Boolean(question)} title={info?.title || ''} onClose={() => answer(null)}>
        {question && (
          <div className="space-y-3 text-sm">
            {question.detail && <p className="rounded-xl bg-slate-50 p-3 text-slate-700">{question.detail}</p>}
            <button type="button" onClick={() => answer('auto')} className="flex w-full items-start gap-3 rounded-xl border border-farm-700 bg-farm-50 p-3 text-left hover:bg-farm-100">
              <Bot size={20} className="mt-0.5 shrink-0 text-farm-700" />
              <span><span className="block font-semibold text-farm-800">ให้ระบบจัดการ</span><span className="text-slate-600">{info.auto}</span></span>
            </button>
            <button type="button" onClick={() => answer('manual')} className="flex w-full items-start gap-3 rounded-xl border border-slate-200 p-3 text-left hover:bg-slate-50">
              <PencilLine size={20} className="mt-0.5 shrink-0 text-slate-500" />
              <span><span className="block font-semibold text-slate-800">จัดการเอง</span><span className="text-slate-600">{info.manual}</span></span>
            </button>
            <label className="flex items-center gap-2 pt-1 text-slate-600">
              <input type="checkbox" checked={remember} onChange={(event) => { setRemember(event.target.checked); setError(''); }} className="h-4 w-4" />
              ใช้ตัวเลือกนี้เสมอ (เปลี่ยนได้ที่หน้าตั้งค่า)
            </label>
            {error && <p role="alert" className="rounded-xl bg-rose-50 p-3 text-rose-700">{error}</p>}
          </div>
        )}
      </Modal>
    </AutomationContext.Provider>
  );
}

export const useAutomation = () => useContext(AutomationContext);
