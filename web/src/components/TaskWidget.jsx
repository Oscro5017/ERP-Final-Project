import { useState, useEffect } from 'react';
import { CheckCircle2, Circle, Clock, Plus, ArrowRight, Calendar, AlertCircle } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { api } from '../lib/api';
import { formatThaiDate, getLocalDateString, getRelativeDayLabel } from '../utils/dateUtils';
import PlantingPrompt from './PlantingPrompt';
import ThaiDateInput from './ThaiDateInput';
import { MASKED_TEXT } from '../utils/masking';

export default function TaskWidget({ onToast }) {
  const navigate = useNavigate();
  const [tasks, setTasks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showAddForm, setShowAddForm] = useState(false);
  const [newTitle, setNewTitle] = useState('');
  const [newDueDate, setNewDueDate] = useState(getLocalDateString());
  const [submitting, setSubmitting] = useState(false);
  const [plantingLineId, setPlantingLineId] = useState(null);

  const loadTasks = async () => {
    try {
      setLoading(true);
      // Fetch pending tasks
      const allPending = await api('/tasks?status=pending');
      const nextWeek = new Date();
      nextWeek.setDate(nextWeek.getDate() + 7);
      const nextWeekStr = getLocalDateString(nextWeek);

      // Filter tasks due <= today + 7 days
      const filtered = allPending.filter((t) => t.due_date <= nextWeekStr);
      setTasks(filtered);
    } catch (err) {
      if (onToast) onToast(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadTasks();
  }, []);

  const handleMarkDone = async (task) => {
    try {
      // Optimistic update
      setTasks((prev) => prev.filter((t) => t.id !== task.id));
      const updated = await api(`/tasks/${task.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ status: 'done' }),
      });
      if (updated.planting_ready) setPlantingLineId(updated.order_line_id);
      if (onToast) onToast(`เสร็จสิ้นงาน: "${task.is_masked ? MASKED_TEXT : task.title}"`);
    } catch (err) {
      if (onToast) onToast(err.message);
      await loadTasks();
    }
  };

  const handleQuickAdd = async (e) => {
    e.preventDefault();
    if (!newTitle.trim()) return;
    try {
      setSubmitting(true);
      await api('/tasks', {
        method: 'POST',
        body: JSON.stringify({
          title: newTitle.trim(),
          due_date: newDueDate,
          status: 'pending',
          source: 'manual',
        }),
      });
      setNewTitle('');
      setShowAddForm(false);
      if (onToast) onToast('เพิ่มงานใหม่สำเร็จ');
      await loadTasks();
    } catch (err) {
      if (onToast) onToast(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-soft">
      <PlantingPrompt
        lineId={plantingLineId}
        onClose={() => setPlantingLineId(null)}
        onCreated={(count) => { setPlantingLineId(null); if (onToast) onToast(`สร้างรอบปลูก ${count} รอบแล้ว`); loadTasks(); }}
      />
      <div className="mb-4 flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="text-lg font-semibold text-slate-800">งานที่ต้องทำ (7 วันนี้)</h3>
            <span className="inline-flex h-6 w-6 items-center justify-center rounded-full bg-amber-100 text-xs font-bold text-amber-800">
              {tasks.length}
            </span>
          </div>
          <p className="text-sm text-slate-500">แจ้งเตือนกิจกรรมที่ต้องลงมือทำตามกำหนด</p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowAddForm((v) => !v)}
            className="inline-flex items-center gap-1 rounded-xl border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs font-medium text-slate-700 transition hover:bg-slate-100"
          >
            <Plus size={14} />
            เพิ่มงาน
          </button>
          <button
            onClick={() => navigate('/activities')}
            className="inline-flex items-center gap-1 rounded-xl bg-farm-50 px-3 py-1.5 text-xs font-semibold text-farm-700 transition hover:bg-farm-100"
          >
            ดูงานทั้งหมด
            <ArrowRight size={14} />
          </button>
        </div>
      </div>

      {showAddForm && (
        <form onSubmit={handleQuickAdd} className="mb-4 rounded-xl border border-emerald-200 bg-emerald-50/60 p-3">
          <p className="mb-2 text-xs font-semibold text-emerald-800">เพิ่มงานใหม่ (บันทึกเอง)</p>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <input
              type="text"
              placeholder="ชื่องาน เช่น ตรวจสอบระบบน้ำ, ผสมปุ๋ยรอบใหม่..."
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
              className="flex-1 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm outline-none focus:border-farm-600"
              autoFocus
            />
            <ThaiDateInput
              value={newDueDate}
              onChange={setNewDueDate}
              label="วันครบกำหนด"
              className="min-w-[150px]"
            />
            <div className="flex gap-2">
              <button
                type="submit"
                disabled={submitting || !newTitle.trim()}
                className="rounded-lg bg-farm-700 px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-farm-800 disabled:opacity-50"
              >
                {submitting ? 'กำลังบันทึก...' : 'บันทึก'}
              </button>
              <button
                type="button"
                onClick={() => setShowAddForm(false)}
                className="rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-600 hover:bg-slate-50"
              >
                ยกเลิก
              </button>
            </div>
          </div>
        </form>
      )}

      {loading ? (
        <div className="py-8 text-center text-sm text-slate-400">กำลังโหลดรายการงาน...</div>
      ) : tasks.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-xl bg-slate-50 py-8 text-center">
          <CheckCircle2 size={36} className="mb-2 text-emerald-500" />
          <p className="text-sm font-semibold text-slate-700">ไม่มีงานค้างในช่วง 7 วันนี้</p>
          <p className="text-xs text-slate-400">จัดการงานเรียบร้อยแล้ว หรือเพิ่มงานใหม่ได้จากปุ่มด้านบน</p>
        </div>
      ) : (
        <div className="space-y-2.5">
          {tasks.map((task) => {
            const relLabel = getRelativeDayLabel(task.due_date);
            const isOverdue = relLabel.includes('เกินกำหนด');
            const isToday = relLabel === 'วันนี้';

            return (
              <div
                key={task.id}
                className={`group flex items-center justify-between rounded-xl border p-3 transition ${
                  isOverdue
                    ? 'border-rose-200 bg-rose-50/40 hover:bg-rose-50'
                    : isToday
                    ? 'border-amber-200 bg-amber-50/30 hover:bg-amber-50/60'
                    : 'border-slate-200 bg-slate-50 hover:bg-slate-100/80'
                }`}
              >
                <div className="flex items-center gap-3">
                  <button
                    onClick={() => handleMarkDone(task)}
                    title="คลิกเพื่อทำเสร็จ"
                    className="flex h-6 w-6 items-center justify-center rounded-full text-slate-400 transition hover:scale-110 hover:text-emerald-600"
                  >
                    <Circle size={20} />
                  </button>
                  <div>
                    <div className="flex items-center gap-2">
                      <p className="text-sm font-semibold text-slate-800">{task.is_masked ? MASKED_TEXT : task.title}</p>
                      {task.cycle_info && (
                        <span className="rounded bg-emerald-100/80 px-1.5 py-0.5 text-[10px] font-medium text-emerald-800">
                          รอบ {task.cycle_info.cycle_code}
                          {task.cycle_info.table_number ? ` (โต๊ะ ${task.cycle_info.table_number})` : ''}
                        </span>
                      )}
                      {task.source === 'auto' ? (
                        <span className="rounded bg-blue-50 px-1.5 py-0.5 text-[10px] font-medium text-blue-700">
                          ระบบอัตโนมัติ
                        </span>
                      ) : (
                        <span className="rounded bg-slate-200/70 px-1.5 py-0.5 text-[10px] font-medium text-slate-600">
                          บันทึกเอง
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-2 text-xs text-slate-500">
                      <Calendar size={12} />
                      <span>{formatThaiDate(task.due_date)}</span>
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <span
                    className={`rounded-full px-2.5 py-1 text-xs font-semibold ${
                      isOverdue
                        ? 'bg-rose-100 text-rose-700'
                        : isToday
                        ? 'bg-amber-100 text-amber-800'
                        : 'bg-slate-200 text-slate-700'
                    }`}
                  >
                    {relLabel}
                  </span>
                  <button
                    onClick={() => handleMarkDone(task)}
                    className="hidden rounded-lg bg-emerald-600 px-2.5 py-1 text-xs font-medium text-white transition hover:bg-emerald-700 group-hover:inline-block"
                  >
                    เสร็จ
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
