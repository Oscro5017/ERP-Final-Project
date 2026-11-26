import { useEffect, useState } from 'react';
import { Check, Clock3, Pencil, Plus, RefreshCw, Search, Trash2, X } from 'lucide-react';
import { api, getRole } from '../../lib/api';
import { formatThaiDate, getLocalDateString, getRelativeDayLabel } from '../../utils/dateUtils';
import PlantingPrompt from '../../components/PlantingPrompt';
import ThaiDateInput from '../../components/ThaiDateInput';

const emptyForm = () => ({ title: '', due_date: getLocalDateString(), cycle_id: '' });

function Activities() {
  const [tasks, setTasks] = useState([]);
  const [cycles, setCycles] = useState([]);
  const [filter, setFilter] = useState('all');
  const [search, setSearch] = useState('');
  const [form, setForm] = useState(emptyForm);
  const [editingId, setEditingId] = useState(null);
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [message, setMessage] = useState('');
  const [plantingLineId, setPlantingLineId] = useState(null);
  const isOwner = getRole() === 'owner';

  const loadData = async (searchText = search, statusFilter = filter) => {
    setIsLoading(true);
    try {
      const params = new URLSearchParams();
      if (statusFilter !== 'all') params.set('status', statusFilter);
      if (isOwner && searchText.trim()) params.set('q', searchText.trim());
      const taskPath = params.size ? `/tasks?${params.toString()}` : '/tasks';
      const [taskData, cycleData] = await Promise.all([api(taskPath), api('/crop-cycles')]);
      setTasks(taskData);
      setCycles(cycleData);
      setMessage('');
    } catch (error) {
      setMessage(error.message);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    const timer = setTimeout(() => loadData(search, filter), 250);
    return () => clearTimeout(timer);
  }, [search, filter]);

  const visibleTasks = tasks;

  const openCreateForm = () => {
    setEditingId(null);
    setForm(emptyForm());
    setIsFormOpen(true);
    setMessage('');
  };

  const openEditForm = (task) => {
    if (task.is_masked) return;
    setEditingId(task.id);
    setForm({ title: task.title, due_date: task.due_date, cycle_id: task.cycle_id ? String(task.cycle_id) : '' });
    setIsFormOpen(true);
    setMessage('');
  };

  const saveTask = async (event) => {
    event.preventDefault();
    if (!form.title.trim() || !form.due_date) return;
    setIsSaving(true);
    setMessage('');
    const payload = {
      title: form.title.trim(),
      due_date: form.due_date,
      cycle_id: form.cycle_id ? Number(form.cycle_id) : null,
    };
    try {
      if (editingId) {
        await api(`/tasks/${editingId}`, { method: 'PATCH', body: JSON.stringify(payload) });
        setMessage('บันทึกการแก้ไขแล้ว');
      } else {
        await api('/tasks', { method: 'POST', body: JSON.stringify({ ...payload, status: 'pending', source: 'manual' }) });
        setMessage('เพิ่มงานแล้ว');
      }
      setIsFormOpen(false);
      await loadData();
    } catch (error) {
      setMessage(error.message);
    } finally {
      setIsSaving(false);
    }
  };

  const updateTaskStatus = async (task) => {
    const nextStatus = task.status === 'done' ? 'pending' : 'done';
    try {
      const updated = await api(`/tasks/${task.id}`, { method: 'PATCH', body: JSON.stringify({ status: nextStatus }) });
      setTasks((current) => current.map((item) => item.id === task.id ? updated : item));
      if (updated.planting_ready) setPlantingLineId(updated.order_line_id);
    } catch (error) {
      setMessage(error.message);
    }
  };

  const deleteTask = async (task) => {
    if (!window.confirm(`ลบงาน “${task.is_masked ? 'ข้อมูลเข้ารหัส' : task.title}” ใช่หรือไม่`)) return;
    try {
      await api(`/tasks/${task.id}`, { method: 'DELETE' });
      setTasks((current) => current.filter((item) => item.id !== task.id));
      setMessage('ลบงานแล้ว');
    } catch (error) {
      setMessage(error.message);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-slate-800">งานฟาร์ม</h1>
          <p className="mt-1 text-sm text-slate-500">งานอัตโนมัติจากรอบปลูกและงานที่บันทึกเอง</p>
        </div>
        <button onClick={openCreateForm} className="inline-flex items-center justify-center gap-2 rounded-xl bg-farm-700 px-4 py-2.5 text-sm font-semibold text-white">
          <Plus size={16} /> เพิ่มงาน
        </button>
      </div>

      {message && <p role="status" className="rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600">{message}</p>}

      {isFormOpen && (
        <form onSubmit={saveTask} className="space-y-4 rounded-2xl border border-slate-200 bg-white p-5 shadow-soft">
          <div className="flex items-center justify-between">
            <h2 className="font-semibold text-slate-800">{editingId ? 'แก้ไขงาน' : 'เพิ่มงานที่บันทึกเอง'}</h2>
            <button type="button" onClick={() => setIsFormOpen(false)} className="rounded-lg p-1 text-slate-500 hover:bg-slate-100" aria-label="ปิดฟอร์ม"><X size={18} /></button>
          </div>
          <div className="grid gap-3 md:grid-cols-[1fr_190px_1fr_auto]">
            <input value={form.title} onChange={(event) => setForm((current) => ({ ...current, title: event.target.value }))} required maxLength={200} placeholder="ชื่องาน" className="rounded-xl border border-slate-200 px-3 py-2 text-sm" />
            <ThaiDateInput value={form.due_date} onChange={(value) => setForm((current) => ({ ...current, due_date: value }))} required label="วันครบกำหนด" />
            <select value={form.cycle_id} onChange={(event) => setForm((current) => ({ ...current, cycle_id: event.target.value }))} className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm">
              <option value="">ไม่ผูกกับรอบปลูก</option>
              {cycles.map((cycle) => <option key={cycle.id} value={cycle.id}>โต๊ะ {cycle.table.table_number} · {cycle.crop_type.name} · {cycle.cycle_code}</option>)}
            </select>
            <button disabled={isSaving} className="rounded-xl bg-farm-700 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">{isSaving ? 'กำลังบันทึก…' : 'บันทึก'}</button>
          </div>
        </form>
      )}

      <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-soft">
        <div className="flex flex-col gap-3 border-b border-slate-100 p-4 md:flex-row md:items-center md:justify-between">
          {isOwner && <div className="flex flex-1 items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 md:max-w-md">
            <Search size={16} className="text-slate-400" />
            <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="ค้นหาชื่องาน โต๊ะ หรือรอบปลูก" className="w-full bg-transparent text-sm outline-none" />
          </div>}
          <div className="flex items-center gap-1 rounded-xl bg-slate-100 p-1" aria-label="กรองสถานะงาน">
            {[['all', 'ทั้งหมด'], ['pending', 'ค้างอยู่'], ['done', 'เสร็จแล้ว']].map(([value, label]) => (
              <button key={value} onClick={() => setFilter(value)} className={`rounded-lg px-3 py-1.5 text-xs font-medium ${filter === value ? 'bg-white text-farm-800 shadow-sm' : 'text-slate-500'}`}>{label}</button>
            ))}
          </div>
          <button onClick={loadData} className="inline-flex items-center justify-center rounded-lg p-2 text-slate-500 hover:bg-slate-100" title="รีเฟรชรายการ"><RefreshCw size={16} /></button>
        </div>

        {isLoading ? <p className="p-8 text-center text-sm text-slate-500">กำลังโหลดงาน…</p> : visibleTasks.length === 0 ? (
          <p className="p-10 text-center text-sm text-slate-500">ไม่พบงานในรายการนี้</p>
        ) : (
          <div className="divide-y divide-slate-100">
            {visibleTasks.map((task) => {
              const dueLabel = getRelativeDayLabel(task.due_date);
              const isOverdue = task.status === 'pending' && dueLabel.startsWith('เกินกำหนด');
              return (
                <article key={task.id} className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between">
                  <div className="flex min-w-0 items-start gap-3">
                    <button onClick={() => updateTaskStatus(task)} className={`mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${task.status === 'done' ? 'bg-emerald-100 text-emerald-700' : 'border border-slate-300 text-slate-400 hover:border-emerald-500 hover:text-emerald-600'}`} title={task.status === 'done' ? 'ทำเครื่องหมายว่ายังค้าง' : 'ทำเครื่องหมายว่าเสร็จ'} aria-label={task.status === 'done' ? 'เปลี่ยนกลับเป็นงานค้าง' : 'ทำงานเสร็จ'}>
                      {task.status === 'done' ? <Check size={17} /> : <span className="h-2 w-2 rounded-full bg-current" />}
                    </button>
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <h2 className={`font-medium ${task.status === 'done' ? 'text-slate-400 line-through' : 'text-slate-800'}`}>{task.is_masked ? 'ข้อมูลเข้ารหัส' : task.title}</h2>
                        <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${task.source === 'auto' ? 'bg-sky-50 text-sky-700' : 'bg-slate-100 text-slate-600'}`}>{task.source === 'auto' ? 'อัตโนมัติ' : 'บันทึกเอง'}</span>
                      </div>
                      <p className="mt-1 text-xs text-slate-500">{task.cycle_info ? `โต๊ะ ${task.cycle_info.table_number} · ${task.cycle_info.crop_name} · รอบ ${task.cycle_info.cycle_code}` : 'ไม่ผูกกับรอบปลูก'}</p>
                    </div>
                  </div>
                  <div className="flex items-center justify-between gap-4 sm:justify-end">
                    <div className={`flex items-center gap-1.5 text-xs ${isOverdue ? 'font-semibold text-rose-600' : 'text-slate-500'}`}>
                      <Clock3 size={14} /> <span>{formatThaiDate(task.due_date)} · {dueLabel}</span>
                    </div>
                    <div className="flex items-center gap-1">
                      {task.planting_ready && <button onClick={() => setPlantingLineId(task.order_line_id)} className="whitespace-nowrap rounded-lg px-2 py-1 text-xs font-semibold text-farm-700 hover:bg-farm-50">สร้างรอบปลูก</button>}
                      {!task.is_masked && <button onClick={() => openEditForm(task)} className="rounded-lg p-2 text-slate-500 hover:bg-slate-100" title="แก้ไขงาน" aria-label="แก้ไขงาน"><Pencil size={15} /></button>}
                      <button onClick={() => deleteTask(task)} className="rounded-lg p-2 text-rose-500 hover:bg-rose-50" title="ลบงาน" aria-label="ลบงาน"><Trash2 size={15} /></button>
                    </div>
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </section>

      <PlantingPrompt
        lineId={plantingLineId}
        onClose={() => setPlantingLineId(null)}
        onCreated={async (count) => { setPlantingLineId(null); await loadData(); setMessage(`สร้างรอบปลูก ${count} รอบแล้ว`); }}
      />
    </div>
  );
}

export default Activities;