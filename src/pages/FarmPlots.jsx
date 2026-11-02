import { useEffect, useMemo, useState } from 'react';
import { Plus, Search } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import StatusBadge from '../components/StatusBadge';
import DataTable from '../components/DataTable';
import Modal from '../components/Modal';
import Toast from '../components/Toast';
import { cropCycleStatuses, cropCycleStatusLabels } from '../constants/cropCycleStatus';
import { api } from '../lib/api';
import { formatThaiDate, getNextTuesday } from '../utils/dateUtils';
import ThaiDateInput from '../components/ThaiDateInput';

const emptyForm = {
  table_id: '',
  batch_id: '',
  crop_type_id: '',
  nursery_start: '',
  harvest_quantity_kg: '',
  status: 'nursery',
};

function FarmPlots() {
  const navigate = useNavigate();
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState('ทั้งหมด');
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [toast, setToast] = useState('');
  const [plots, setPlots] = useState([]);
  const [references, setReferences] = useState({ tables: [], batches: [], cropTypes: [] });
  const [editingPlot, setEditingPlot] = useState(null);
  const [formData, setFormData] = useState(emptyForm);

  const showToast = (message) => {
    setToast(message);
    window.setTimeout(() => setToast(''), 1800);
  };

  const loadData = async () => {
    const [cycles, tables, batches, cropTypes] = await Promise.all([
      api('/crop-cycles'),
      api('/tables'),
      api('/batches'),
      api('/crop-types'),
    ]);
    setPlots(cycles);
    setReferences({ tables, batches, cropTypes });
  };

  useEffect(() => {
    loadData().catch((error) => showToast(error.message));
  }, []);

  const filteredPlots = useMemo(() => plots.filter((item) => {
    const searchable = [item.cycle_code, item.table.table_number, item.batch.batch_number, item.crop_type.name].join(' ').toLowerCase();
    return searchable.includes(search.toLowerCase()) && (filter === 'ทั้งหมด' || item.status === filter);
  }), [filter, plots, search]);

  const openCreateModal = () => {
    setEditingPlot(null);
    setFormData({ ...emptyForm, nursery_start: getNextTuesday() });
    setIsModalOpen(true);
  };

  const openEditModal = (plot) => {
    setEditingPlot(plot.id);
    setFormData({
      table_id: plot.table_id,
      batch_id: plot.batch_id,
      crop_type_id: plot.crop_type_id,
      nursery_start: plot.nursery_start,
      harvest_quantity_kg: plot.harvest_quantity_kg ?? '',
      status: plot.status,
    });
    setIsModalOpen(true);
  };

  const handleSubmit = async () => {
    if (!formData.table_id || !formData.batch_id || !formData.crop_type_id || !formData.nursery_start) {
      showToast('กรุณากรอกข้อมูลให้ครบถ้วน');
      return;
    }
    const payload = {
      ...formData,
      table_id: Number(formData.table_id),
      batch_id: Number(formData.batch_id),
      crop_type_id: Number(formData.crop_type_id),
      harvest_quantity_kg: formData.harvest_quantity_kg === '' ? null : Number(formData.harvest_quantity_kg),
    };
    try {
      if (editingPlot) {
        await api(`/crop-cycles/${editingPlot}`, {
          method: 'PATCH',
          body: JSON.stringify({ status: payload.status, nursery_start: payload.nursery_start, harvest_quantity_kg: payload.harvest_quantity_kg }),
        });
        showToast('แก้ไขแปลงสำเร็จ');
      } else {
        await api('/crop-cycles', { method: 'POST', body: JSON.stringify(payload) });
        showToast('เพิ่มแปลงเพาะปลูกสำเร็จ');
      }
      await loadData();
      setIsModalOpen(false);
    } catch (error) {
      showToast(error.message);
    }
  };

  const handleDelete = async (row) => {
    if (!window.confirm(`ต้องการลบโต๊ะ ${row.table_number} หรือไม่`)) return;
    try {
      await api(`/crop-cycles/${row.id}`, { method: 'DELETE' });
      setPlots((previous) => previous.filter((plot) => plot.id !== row.id));
      showToast(`ลบรอบ ${row.cycle_code} แล้ว`);
    } catch (error) {
      showToast(error.message);
    }
  };

  const columns = [
    { key: 'cycle_code', label: 'รหัสรอบ' },
    { key: 'table', label: 'โต๊ะ' },
    { key: 'crop', label: 'ชนิดพืช' },
    { key: 'batch', label: 'แบตช์' },
    { key: 'nursery_start', label: 'เริ่มอนุบาล' },
    { key: 'status', label: 'สถานะ' },
  ];
  const rows = filteredPlots.map((item) => ({
    ...item,
    table_id: item.table.id,
    batch_id: item.batch.id,
    crop_type_id: item.crop_type.id,
    table_number: item.table.table_number,
    table: `โต๊ะ ${item.table.table_number}`,
    crop: item.crop_type.name,
    batch: `แบตช์ ${item.batch.batch_number}`,
    nursery_start: formatThaiDate(item.nursery_start),
    status: <StatusBadge status={cropCycleStatusLabels[item.status]} />,
  }));

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div><h1 className="text-2xl font-semibold text-slate-800">แปลงเพาะปลูก</h1><p className="text-sm text-slate-500">จัดการข้อมูลรอบการปลูกจากระบบจริง</p></div>
        <button onClick={openCreateModal} className="inline-flex items-center gap-2 rounded-xl bg-farm-700 px-4 py-2.5 text-sm font-semibold text-white shadow-soft"><Plus size={16} />เพิ่มแปลงเพาะปลูก</button>
      </div>
      <div className="flex flex-col gap-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-soft md:flex-row md:items-center md:justify-between">
        <div className="flex flex-1 items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2"><Search size={16} className="text-slate-400" /><input value={search} onChange={(event) => setSearch(event.target.value)} className="w-full bg-transparent text-sm outline-none" placeholder="ค้นหารหัสรอบ โต๊ะ แบตช์ หรือพืช" /></div>
        <select value={filter} onChange={(event) => setFilter(event.target.value)} className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-600"><option value="ทั้งหมด">ทั้งหมด</option>{cropCycleStatuses.map((status) => <option key={status.value} value={status.value}>{status.label}</option>)}</select>
      </div>
      <DataTable columns={columns} rows={rows} onView={(row) => navigate(`/plots/${row.id}`)} onEdit={openEditModal} onDelete={handleDelete} />
      <Modal isOpen={isModalOpen} title={editingPlot ? 'แก้ไขแปลงเพาะปลูก' : 'เพิ่มแปลงเพาะปลูก'} onClose={() => setIsModalOpen(false)}>
        <div className="space-y-3">
          <select value={formData.table_id} onChange={(event) => setFormData((previous) => ({ ...previous, table_id: event.target.value }))} className="w-full rounded-xl border border-slate-200 px-3 py-2"><option value="">เลือกโต๊ะ</option>{references.tables.map((table) => <option key={table.id} value={table.id}>โต๊ะ {table.table_number}</option>)}</select>
          <select value={formData.batch_id} onChange={(event) => setFormData((previous) => ({ ...previous, batch_id: event.target.value }))} className="w-full rounded-xl border border-slate-200 px-3 py-2"><option value="">เลือกแบตช์</option>{references.batches.map((batch) => <option key={batch.id} value={batch.id}>แบตช์ {batch.batch_number}</option>)}</select>
          <select value={formData.crop_type_id} onChange={(event) => setFormData((previous) => ({ ...previous, crop_type_id: event.target.value }))} className="w-full rounded-xl border border-slate-200 px-3 py-2"><option value="">เลือกชนิดพืช</option>{references.cropTypes.map((cropType) => <option key={cropType.id} value={cropType.id}>{cropType.name}</option>)}</select>
          <ThaiDateInput value={formData.nursery_start} onChange={(value) => setFormData((previous) => ({ ...previous, nursery_start: value }))} className="w-full" label="วันที่เริ่มอนุบาล" />
          <select value={formData.status} onChange={(event) => setFormData((previous) => ({ ...previous, status: event.target.value }))} className="w-full rounded-xl border border-slate-200 px-3 py-2">{cropCycleStatuses.map((status) => <option key={status.value} value={status.value}>{status.label}</option>)}</select>
          {(editingPlot || formData.status === 'harvested') && <input type="number" min="0" step="0.1" value={formData.harvest_quantity_kg} onChange={(event) => setFormData((previous) => ({ ...previous, harvest_quantity_kg: event.target.value }))} className="w-full rounded-xl border border-slate-200 px-3 py-2" placeholder="ผลผลิตจริง (กก.)" aria-label="ผลผลิตจริง (กิโลกรัม)" />}
          <button onClick={handleSubmit} className="rounded-xl bg-farm-700 px-4 py-2 text-sm font-semibold text-white">บันทึก</button>
        </div>
      </Modal>
      <Toast message={toast} visible={Boolean(toast)} />
    </div>
  );
}

export default FarmPlots;
