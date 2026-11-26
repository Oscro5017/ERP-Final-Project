import { useEffect, useState } from 'react';
import { useAutomation } from './AutomationPrompt';
import { AlertTriangle, Sprout } from 'lucide-react';
import Modal from './Modal';
import ThaiDateInput from './ThaiDateInput';
import { api } from '../lib/api';
import { formatThaiDate } from '../utils/dateUtils';

/** Asks whether to create crop cycles after an order's planting activity is done. */
function PlantingPrompt({ lineId, onClose, onCreated }) {
  const { ask } = useAutomation();
  const [isManual, setIsManual] = useState(false);
  const [plan, setPlan] = useState(null);
  const [tableIds, setTableIds] = useState([]);
  const [startDate, setStartDate] = useState('');
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    let ignore = false;
    setPlan(null);
    setIsManual(false);
    setError('');
    if (!lineId) return undefined;
    api(`/sales-orders/lines/${lineId}/planting`)
      .then(async (data) => {
        if (ignore) return;
        setPlan(data);
        setTableIds(data.suggested_table_ids);
        setStartDate(data.nursery_start);
        // Only offer to do it all when nothing needs the user's judgement.
        const isClear = data.can_create && !data.is_late && data.tables_needed && data.free_tables.length >= data.tables_needed;
        if (!isClear) {
          setIsManual(true);
          return;
        }
        const mode = await ask('planting_cycles', `${data.crop_name} ต้องปลูก ${data.to_plant} ${data.unit} ใช้ ${data.tables_needed} โต๊ะ · ${data.order_no}`);
        if (ignore) return;
        if (mode === 'auto') await create(data.suggested_table_ids, data.nursery_start);
        else if (mode === 'manual') setIsManual(true);
        else onClose();
      })
      .catch((err) => { if (!ignore) { setError(err.message); setIsManual(true); } });
    return () => { ignore = true; };
  }, [lineId]);

  const toggleTable = (id) => setTableIds((current) => (
    current.includes(id) ? current.filter((item) => item !== id) : [...current, id]
  ));

  const create = async (tables, start) => {
    const tasks = await ask('cycle_tasks', `รอบปลูก ${tables.length} โต๊ะ`);
    if (!tasks) {
      setIsManual(true);
      return;
    }
    setIsSaving(true);
    setError('');
    try {
      const result = await api(`/sales-orders/lines/${lineId}/planting`, {
        method: 'POST',
        body: JSON.stringify({ table_ids: tables, nursery_start: start, create_tasks: tasks === 'auto' }),
      });
      onCreated(result.cycle_ids.length);
    } catch (err) {
      setError(err.message);
      setIsManual(true);
    } finally {
      setIsSaving(false);
    }
  };

  const shortOfTables = plan?.tables_needed && plan.free_tables.length < plan.tables_needed;

  return (
    <Modal isOpen={Boolean(lineId) && isManual} title="สร้างรอบปลูกให้เลยไหม?" onClose={isSaving ? () => {} : onClose}>
      <div className="max-h-[65vh] space-y-4 overflow-y-auto text-sm text-slate-700">
        {!plan && !error && <p className="py-4 text-center text-slate-500">กำลังคำนวณแผนปลูก…</p>}
        {plan && (
          <>
            <div className="flex gap-3 rounded-xl bg-farm-50 p-3">
              <Sprout size={20} className="mt-0.5 shrink-0 text-farm-700" />
              <div>
                <p className="font-semibold text-slate-800">{plan.crop_name} ต้องปลูก {plan.to_plant} จาก {plan.quantity} {plan.unit} · {plan.order_no}</p>
                <p>ส่ง {formatThaiDate(plan.delivery_date)}</p>
                {startDate === plan.nursery_start && <p>เพาะวันนี้ คาดว่าพร้อมเก็บ {formatThaiDate(plan.expected_ready_date)}</p>}
              </div>
            </div>
            {plan.is_late && startDate === plan.nursery_start && (
              <p className="flex gap-2 rounded-xl border border-amber-200 bg-amber-50 p-3 text-amber-800">
                <AlertTriangle size={16} className="mt-0.5 shrink-0" /> ถ้าเพาะวันนี้ อาจเก็บเกี่ยวไม่ทันวันส่ง
              </p>
            )}
            <div>
              <p className="mb-1 font-medium">วันเริ่มอนุบาล</p>
              <ThaiDateInput value={startDate} onChange={setStartDate} required label="วันเริ่มอนุบาล" />
            </div>
            <div>
              <p className="mb-1 font-medium">โต๊ะปลูก (เลือกแล้ว {tableIds.length})</p>
              <p className="mb-2 text-xs text-slate-500">
                {plan.tables_needed
                  ? `ประมาณจากผลผลิตที่ผ่านมา: ใช้ ${plan.tables_needed} โต๊ะ`
                  : 'ยังไม่มีข้อมูลผลผลิตให้ประมาณจำนวนโต๊ะ กรุณาเลือกเอง'}
              </p>
              {shortOfTables && <p className="mb-2 text-xs text-amber-700">โต๊ะว่างมีแค่ {plan.free_tables.length} โต๊ะ</p>}
              <div className="flex flex-wrap gap-2">
                {plan.free_tables.map((table) => (
                  <button
                    key={table.id}
                    type="button"
                    aria-pressed={tableIds.includes(table.id)}
                    onClick={() => toggleTable(table.id)}
                    className={`min-w-10 rounded-lg border px-2.5 py-1.5 text-sm ${tableIds.includes(table.id) ? 'border-farm-700 bg-farm-700 text-white' : 'border-slate-200 bg-white text-slate-600'}`}
                  >
                    {table.table_number}
                  </button>
                ))}
                {plan.free_tables.length === 0 && <span className="text-rose-600">ไม่มีโต๊ะว่าง</span>}
              </div>
            </div>
          </>
        )}
        {error && <p role="alert" className="rounded-xl bg-rose-50 p-3 text-rose-700">{error}</p>}
      </div>
      <div className="mt-5 flex justify-end gap-2">
        <button type="button" onClick={onClose} disabled={isSaving} className="rounded-xl border border-slate-200 px-4 py-2 text-sm">ไว้ทีหลัง</button>
        <button type="button" onClick={() => create(tableIds, startDate)} disabled={!plan?.can_create || !tableIds.length || !startDate || isSaving} className="rounded-xl bg-farm-700 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">
          {isSaving ? 'กำลังสร้าง…' : 'สร้างรอบปลูก'}
        </button>
      </div>
    </Modal>
  );
}

export default PlantingPrompt;
