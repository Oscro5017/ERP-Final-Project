import { useEffect, useMemo, useState } from 'react';
import { ChevronDown, ChevronUp, Pencil, Plus, Sprout, Trash2 } from 'lucide-react';
import { useParams } from 'react-router-dom';
import AutocompleteInput from '../../components/AutocompleteInput';
import { useAutomation } from '../../components/AutomationPrompt';
import Modal from '../../components/Modal';
import StatusBadge from '../../components/StatusBadge';
import ThaiDateInput from '../../components/ThaiDateInput';
import { cropCycleStatusLabels } from '../../constants/cropCycleStatus';
import { api } from '../../lib/api';
import { fetchAll } from '../../lib/lookups';
import { itemName } from '../../utils/itemCategories';
import { formatThaiDate, formatThaiDateTime } from '../../utils/dateUtils';

// Stock source of a mixed item: '' keeps the mapping remembered for its name.
const stockChoice = (item) => {
  if (!item.stock) return {};
  return { product_id: item.stock === 'none' ? null : Number(item.stock) };
};

function StockSelect({ value, products, onChange }) {
  return (
    <select aria-label="ตัดสต็อกจาก" value={value || ''} onChange={(event) => onChange(event.target.value)} className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm">
      <option value="">ตัดสต็อกตามที่เคยเลือกไว้กับชื่อนี้</option>
      <option value="none">ไม่ตัดสต็อก</option>
      {products.map((product) => <option key={product.id} value={product.id}>ตัดจาก {itemName(product)} (เหลือ {product.on_hand} {product.unit})</option>)}
    </select>
  );
}

function PlotDetail() {
  const { ask } = useAutomation();
  const [stockItems, setStockItems] = useState([]);
  const { id } = useParams();
  const [plot, setPlot] = useState(null);
  const [harvestQuantity, setHarvestQuantity] = useState('');
  const [isSavingHarvestQuantity, setIsSavingHarvestQuantity] = useState(false);
  const [inputApplications, setInputApplications] = useState([]);
  const [statusLogs, setStatusLogs] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState('');
  const [form, setForm] = useState({
    applied_date: new Date().toISOString().slice(0, 10),
    category: '',
    note: '',
    items: [{ item_name: '', quantity: 1, unit: '' }],
  });

  // Expand/Collapse state for history items (default to open for all)
  const [expandedIds, setExpandedIds] = useState({});

  // Edit modal state
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  const [editingAppId, setEditingAppId] = useState(null);
  const [isSavingEdit, setIsSavingEdit] = useState(false);
  const [editError, setEditError] = useState('');
  const [editForm, setEditForm] = useState({
    applied_date: '',
    category: '',
    note: '',
    items: [],
  });

  useEffect(() => {
    fetchAll('/products')
      .then((items) => setStockItems(items.filter((item) => item.is_active !== false && item.category !== 'vegetable')))
      .catch(() => {});
  }, []);

  const stockFields = (item, productId) => {
    const product = stockItems.find((entry) => String(entry.id) === productId);
    if (!product) return { stock: productId };
    return {
      stock: productId,
      unit: product.unit,
      ...(item.item_name || product.is_masked ? {} : { item_name: product.name }),
    };
  };

  useEffect(() => {
    setIsLoading(true);
    api('/crop-cycles')
      .then(async (cycles) => {
        const matchingPlot = cycles.find((cycle) => String(cycle.id) === id);
        setPlot(matchingPlot || null);
        if (matchingPlot) {
          setHarvestQuantity(matchingPlot.harvest_quantity_kg ?? '');
          const [applications, logs] = await Promise.all([
            api(`/crop-cycles/${matchingPlot.id}/input-applications`),
            api(`/crop-cycles/${matchingPlot.id}/status-log`),
          ]);
          return { applications, logs };
        }
        return { applications: [], logs: [] };
      })
      .then(({ applications, logs }) => {
        const apps = applications || [];
        setInputApplications(apps);
        setStatusLogs(logs || []);
        // Default all to expanded
        const initialExpanded = {};
        apps.forEach((app) => {
          initialExpanded[app.id] = true;
        });
        setExpandedIds(initialExpanded);
      })
      .catch((requestError) => setError(requestError.message))
      .finally(() => setIsLoading(false));
  }, [id]);

  const totalApplications = useMemo(() => inputApplications.length, [inputApplications]);

  const saveHarvestQuantity = async () => {
    if (!plot) return;
    const quantity = harvestQuantity === '' ? null : Number(harvestQuantity);
    const choices = {};
    if (plot.crop_type.product_id && quantity > 0) {
      const mode = await ask('harvest_stock', `${plot.crop_type.name} ${quantity} กก.`);
      if (!mode) return;
      choices.record_harvest_stock = mode === 'auto';
    }
    setIsSavingHarvestQuantity(true);
    try {
      const updated = await api(`/crop-cycles/${plot.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ harvest_quantity_kg: quantity, ...choices }),
      });
      setPlot(updated);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setIsSavingHarvestQuantity(false);
    }
  };

  const toggleExpand = (appId) => {
    setExpandedIds((prev) => ({
      ...prev,
      [appId]: !prev[appId],
    }));
  };

  const updateItem = (index, field, value) => {
    setForm((current) => ({
      ...current,
      items: current.items.map((item, itemIndex) => itemIndex === index ? { ...item, [field]: value } : item),
    }));
  };

  const addItemRow = () => {
    setForm((current) => ({
      ...current,
      items: [...current.items, { item_name: '', quantity: 1, unit: '' }],
    }));
  };

  const removeItemRow = (index) => {
    setForm((current) => ({
      ...current,
      items: current.items.filter((_, itemIndex) => itemIndex !== index),
    }));
  };

  const submitApplication = async () => {
    if (!plot) return;
    const payload = {
      applied_date: form.applied_date,
      category: form.category || 'ปุ๋ย',
      note: form.note || null,
      items: form.items
        .filter((item) => item.item_name && item.item_name.trim())
        .map((item) => ({
          item_name: item.item_name.trim(),
          quantity: Number(item.quantity || 0),
          unit: item.unit.trim(),
          ...stockChoice(item),
        })),
    };

    if (!payload.items.length) {
      setError('กรุณาเพิ่มรายการปุ๋ย/ยาอย่างน้อย 1 รายการ');
      return;
    }

    setIsSaving(true);
    setError('');
    try {
      const created = await api(`/crop-cycles/${plot.id}/input-applications`, {
        method: 'POST',
        body: JSON.stringify(payload),
      });
      setInputApplications((current) => [created, ...current]);
      setExpandedIds((prev) => ({ ...prev, [created.id]: true }));
      setForm({
        applied_date: new Date().toISOString().slice(0, 10),
        category: '',
        note: '',
        items: [{ item_name: '', quantity: 1, unit: '' }],
      });
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setIsSaving(false);
    }
  };

  const handleDeleteApplication = async (appId) => {
    if (!window.confirm('คุณต้องการลบรายการบันทึกปุ๋ย/ยานี้ใช่หรือไม่?')) {
      return;
    }

    try {
      await api(`/input-applications/${appId}`, { method: 'DELETE' });
      setInputApplications((current) => current.filter((app) => app.id !== appId));
    } catch (deleteError) {
      alert(`ลบรายการไม่สำเร็จ: ${deleteError.message}`);
    }
  };

  const openEditModal = (application) => {
    setEditingAppId(application.id);
    setEditForm({
      applied_date: application.applied_date,
      category: application.category || '',
      note: application.note || '',
      items: (application.items || []).map((item) => ({
        stock: item.product_id ? String(item.product_id) : 'none',
        item_name: item.item_name,
        quantity: item.quantity,
        unit: item.unit || '',
      })),
    });
    setEditError('');
    setIsEditModalOpen(true);
  };

  const updateEditItem = (index, field, value) => {
    setEditForm((current) => ({
      ...current,
      items: current.items.map((item, itemIndex) => itemIndex === index ? { ...item, [field]: value } : item),
    }));
  };

  const addEditItemRow = () => {
    setEditForm((current) => ({
      ...current,
      items: [...current.items, { item_name: '', quantity: 1, unit: '' }],
    }));
  };

  const removeEditItemRow = (index) => {
    setEditForm((current) => ({
      ...current,
      items: current.items.filter((_, itemIndex) => itemIndex !== index),
    }));
  };

  const submitEditApplication = async () => {
    const validItems = editForm.items
      .filter((item) => item.item_name && item.item_name.trim())
      .map((item) => ({
        item_name: item.item_name.trim(),
        quantity: Number(item.quantity || 0),
        unit: item.unit.trim(),
        ...stockChoice(item),
      }));

    if (!validItems.length) {
      setEditError('กรุณาเพิ่มรายการปุ๋ย/ยาอย่างน้อย 1 รายการ');
      return;
    }

    setIsSavingEdit(true);
    setEditError('');
    try {
      const updated = await api(`/input-applications/${editingAppId}`, {
        method: 'PATCH',
        body: JSON.stringify({
          applied_date: editForm.applied_date,
          category: editForm.category.trim(),
          note: editForm.note.trim() || null,
          items: validItems,
        }),
      });

      setInputApplications((current) =>
        current.map((app) => (app.id === editingAppId ? updated : app))
      );
      setIsEditModalOpen(false);
    } catch (requestError) {
      setEditError(requestError.message);
    } finally {
      setIsSavingEdit(false);
    }
  };

  const renderItemRow = (item, index) => (
    <div key={index} className="grid gap-3 rounded-2xl border border-slate-200 bg-slate-50 p-3 md:grid-cols-[1.6fr_0.8fr_0.9fr_auto]">
      <div>
        <label className="mb-1 block text-xs font-medium text-slate-600">ชื่อวัตถุดิบ</label>
        <AutocompleteInput
          value={item.item_name}
          onChange={(value) => updateItem(index, 'item_name', value)}
          placeholder="เช่น ปุ๋ย A"
          onSuggestionSelect={(suggestion) => {
            updateItem(index, 'item_name', suggestion.item_name);
            if (suggestion.last_unit) updateItem(index, 'unit', suggestion.last_unit);
            if (suggestion.last_category) setForm((current) => ({ ...current, category: suggestion.last_category }));
          }}
        />
      </div>
      <div>
        <label className="mb-1 block text-xs font-medium text-slate-600">ปริมาณ</label>
        <input
          type="number"
          min="0"
          step="0.1"
          value={item.quantity}
          onChange={(event) => updateItem(index, 'quantity', Number(event.target.value || 0))}
          className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-700 outline-none transition focus:border-farm-500 focus:ring-2 focus:ring-farm-100"
        />
      </div>
      <div>
        <label className="mb-1 block text-xs font-medium text-slate-600">หน่วย</label>
        <AutocompleteInput
          value={item.unit}
          onChange={(value) => updateItem(index, 'unit', value)}
          placeholder="เช่น ลิตร"
          onSuggestionSelect={(suggestion) => updateItem(index, 'unit', suggestion.last_unit || item.unit)}
        />
      </div>
      <div className="flex items-end">
        <button
          type="button"
          onClick={() => removeItemRow(index)}
          disabled={form.items.length === 1}
          className="inline-flex h-11 w-11 items-center justify-center rounded-xl border border-rose-200 bg-rose-50 text-rose-600 transition hover:bg-rose-100 disabled:cursor-not-allowed disabled:opacity-40"
          aria-label="ลบรายการ"
        >
          <Trash2 size={16} />
        </button>
      </div>
      <div className="col-span-full">
        <StockSelect value={item.stock} products={stockItems} onChange={(value) => setForm((current) => ({ ...current, items: current.items.map((row, i) => (i === index ? { ...row, ...stockFields(row, value) } : row)) }))} />
      </div>
    </div>
  );

  if (isLoading) return <p className="text-sm text-slate-500">กำลังโหลดข้อมูล...</p>;
  if (error) return <p className="text-sm text-rose-600">{error}</p>;
  if (!plot) return (
    <div className="rounded-2xl border border-slate-200 bg-white p-8 text-center shadow-soft">
      <h1 className="text-xl font-semibold text-slate-800">ไม่พบข้อมูลรอบการปลูก</h1>
      <p className="mt-2 text-sm text-slate-500">รอบการปลูกนี้อาจถูกลบไปแล้ว หรือ URL ไม่ถูกต้อง</p>
    </div>
  );

  const details = [
    ['รหัสรอบ', plot.cycle_code],
    ['โต๊ะ', `โต๊ะ ${plot.table.table_number}`],
    ['ชนิดพืช', plot.crop_type.name],
    ['แบตช์', `แบตช์ ${plot.batch.batch_number}`],
    ['วันที่เริ่มอนุบาล', formatThaiDate(plot.nursery_start)],
    ['สถานะ', <StatusBadge status={cropCycleStatusLabels[plot.status]} />],
  ];

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-slate-800">รายละเอียดการปลูก - โต๊ะ {plot.table.table_number}</h1>
          <p className="text-sm text-slate-500">ตรวจสอบความคืบหน้าของรอบการปลูก</p>
        </div>
        <div className="rounded-xl bg-emerald-50 px-3 py-2 text-sm font-medium text-emerald-700">
          ประวัติ {totalApplications} รายการ
        </div>
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
        <div className="space-y-6">
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-soft">
            <h3 className="text-lg font-semibold text-slate-800">ข้อมูลการปลูก</h3>
            <div className="mt-4 grid gap-4 md:grid-cols-2">
              {details.map(([label, value]) => (
                <div key={label} className="rounded-xl bg-slate-50 p-3">
                  <p className="text-sm text-slate-500">{label}</p>
                  <div className="mt-1 font-semibold text-slate-800">{value}</div>
                </div>
              ))}
            </div>
          </div>
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-soft">
            <h3 className="text-lg font-semibold text-slate-800">ช่วงเวลา</h3>
            <div className="mt-4 grid gap-3 text-sm text-slate-600">
              <p>เริ่มอนุบาล: {formatThaiDate(plot.nursery_start)}</p>
              <p>ย้ายปลูก: {formatThaiDate(plot.transplant_date)}</p>
              <p>เก็บเกี่ยว: {formatThaiDate(plot.harvest_date)}</p>
            </div>
          </div>
          {plot.status === 'harvested' && (
            <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-soft">
              <label htmlFor="harvest-quantity" className="text-lg font-semibold text-slate-800">ผลผลิตจริง (กก.)</label>
              <div className="mt-3 flex gap-2">
                <input id="harvest-quantity" type="number" min="0" step="0.1" value={harvestQuantity} onChange={(event) => setHarvestQuantity(event.target.value)} className="min-w-0 flex-1 rounded-xl border border-slate-200 px-3 py-2 text-sm" placeholder="ระบุน้ำหนักที่เก็บได้" />
                <button onClick={saveHarvestQuantity} disabled={isSavingHarvestQuantity} className="rounded-xl bg-farm-700 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">{isSavingHarvestQuantity ? 'กำลังบันทึก…' : 'บันทึก'}</button>
              </div>
            </div>
          )}
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-soft">
            <h3 className="text-lg font-semibold text-slate-800">ประวัติสถานะรอบปลูก</h3>
            {statusLogs.length === 0 ? <p className="mt-3 text-sm text-slate-500">ยังไม่มีประวัติสถานะ</p> : (
              <ol className="mt-4 space-y-4 border-l border-emerald-200 pl-4">
                {statusLogs.map((log) => (
                  <li key={log.id} className="relative">
                    <span className="absolute -left-[21px] top-1 h-2.5 w-2.5 rounded-full border-2 border-white bg-emerald-600" />
                    <p className="text-sm font-medium text-slate-800">
                      {log.from_status ? `${cropCycleStatusLabels[log.from_status]} → ` : ''}{cropCycleStatusLabels[log.to_status] || log.to_status}
                    </p>
                    <time className="text-xs text-slate-500">{formatThaiDateTime(log.changed_at)}</time>
                  </li>
                ))}
              </ol>
            )}
          </div>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-soft">
          <h3 className="text-lg font-semibold text-slate-800">วัตถุดิบที่ใช้</h3>
          <div className="mt-4 space-y-3">
            {['เมล็ดพันธุ์', 'ปุ๋ยคอก', 'ปุ๋ยหมัก', 'สารชีวภาพ'].map((name) => (
              <div key={name} className="flex items-center justify-between rounded-xl bg-slate-50 p-3">
                <div className="flex items-center gap-2">
                  <Sprout size={16} className="text-farm-700" />
                  <span className="font-medium text-slate-700">{name}</span>
                </div>
                <span className="text-sm text-slate-500">ยังไม่มีข้อมูล</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ฟอร์มเพิ่มการให้ปุ๋ย/ยา */}
      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-soft">
        <div className="mb-4 flex items-center justify-between gap-3">
          <h3 className="text-lg font-semibold text-slate-800">บันทึกปุ๋ย/ยา</h3>
          <button
            type="button"
            onClick={addItemRow}
            className="inline-flex items-center gap-2 rounded-xl bg-farm-700 px-3 py-2 text-sm font-medium text-white transition hover:bg-farm-800"
          >
            <Plus size={16} /> เพิ่มรายการผสม
          </button>
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-600">วันที่</label>
            <ThaiDateInput
              value={form.applied_date}
              onChange={(value) => setForm((current) => ({ ...current, applied_date: value }))}
              className="w-full"
              label="วันที่"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-600">ประเภท</label>
            <AutocompleteInput
              value={form.category}
              onChange={(value) => setForm((current) => ({ ...current, category: value }))}
              placeholder="เช่น ปุ๋ย / ยา"
              onSuggestionSelect={(suggestion) =>
                setForm((current) => ({ ...current, category: suggestion.last_category || current.category }))
              }
            />
          </div>
        </div>

        <div className="mt-4 space-y-3">
          {form.items.map((item, index) => renderItemRow(item, index))}
        </div>

        <div className="mt-4">
          <label className="mb-1 block text-xs font-medium text-slate-600">หมายเหตุ</label>
          <textarea
            value={form.note}
            onChange={(event) => setForm((current) => ({ ...current, note: event.target.value }))}
            rows="3"
            className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-700 outline-none transition focus:border-farm-500 focus:ring-2 focus:ring-farm-100"
            placeholder="เช่น ใช้ตามสภาพแปลงหลังฝนตก"
          />
        </div>

        <div className="mt-5 flex flex-wrap items-center justify-between gap-3">
          <div className="text-sm text-slate-500">
            รายการทั้งหมด {form.items.filter((item) => item.item_name && item.item_name.trim()).length} รายการ
          </div>
          <button
            type="button"
            onClick={submitApplication}
            disabled={isSaving}
            className="inline-flex items-center gap-2 rounded-xl bg-farm-700 px-4 py-2.5 text-sm font-semibold text-white shadow-soft transition hover:bg-farm-800 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isSaving ? 'กำลังบันทึก...' : 'บันทึกปุ๋ย/ยา'}
          </button>
        </div>
      </div>

      {/* ประวัติการให้ปุ๋ย/ยา (Accordion / Expandable) */}
      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-soft">
        <h3 className="text-lg font-semibold text-slate-800">ประวัติการให้ปุ๋ย/ยา</h3>
        <div className="mt-4 space-y-3">
          {!inputApplications.length && (
            <p className="py-4 text-center text-sm text-slate-500">ยังไม่มีประวัติการให้ปุ๋ย/ยาในรอบนี้</p>
          )}
          {inputApplications.map((application) => {
            const isExpanded = !!expandedIds[application.id];
            const itemCount = application.items ? application.items.length : 0;

            return (
              <div key={application.id} className="overflow-hidden rounded-2xl border border-slate-200 bg-slate-50 transition">
                <div className="flex flex-col gap-3 p-4 md:flex-row md:items-center md:justify-between">
                  <div
                    className="flex cursor-pointer items-center gap-3"
                    onClick={() => toggleExpand(application.id)}
                  >
                    <button
                      type="button"
                      className="inline-flex h-8 w-8 items-center justify-center rounded-lg bg-white text-slate-500 shadow-xs transition hover:bg-slate-100"
                      aria-label="ย่อ/ขยาย"
                    >
                      {isExpanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                    </button>
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-slate-800">{formatThaiDate(application.applied_date)}</span>
                        <span className="rounded-md bg-farm-100 px-2 py-0.5 text-xs font-medium text-farm-800">
                          {application.category || 'ทั่วไป'}
                        </span>
                        <span className="text-xs text-slate-500">({itemCount} รายการผสม)</span>
                      </div>
                      {application.is_masked ? (
                        <p className="mt-0.5 text-xs font-medium text-slate-500">ข้อมูลเข้ารหัส</p>
                      ) : application.note && (
                        <p className="mt-0.5 text-xs text-slate-500 line-clamp-1">หมายเหตุ: {application.note}</p>
                      )}
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    {!application.is_masked && <button
                      type="button"
                      onClick={() => openEditModal(application)}
                      className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-700 shadow-xs transition hover:bg-slate-100"
                    >
                      <Pencil size={12} /> แก้ไข
                    </button>}
                    <button
                      type="button"
                      onClick={() => handleDeleteApplication(application.id)}
                      className="inline-flex items-center gap-1 rounded-lg border border-rose-200 bg-rose-50 px-2.5 py-1.5 text-xs font-medium text-rose-600 shadow-xs transition hover:bg-rose-100"
                    >
                      <Trash2 size={12} /> ลบ
                    </button>
                  </div>
                </div>

                {isExpanded && (
                  <div className="border-t border-slate-200 bg-white px-4 py-3">
                    {application.is_masked ? (
                      <p className="mb-3 rounded-lg border border-slate-100 bg-slate-50 p-2.5 text-xs text-slate-500">หมายเหตุและรายการผสม: ข้อมูลเข้ารหัส</p>
                    ) : application.note && (
                      <p className="mb-3 text-xs text-slate-600 bg-slate-50 p-2.5 rounded-lg border border-slate-100">
                        <span className="font-medium text-slate-700">หมายเหตุ:</span> {application.note}
                      </p>
                    )}
                    <div className="overflow-x-auto">
                      <table className="min-w-full text-left text-sm">
                        <thead className="border-b border-slate-100 bg-slate-50 text-xs font-medium text-slate-500">
                          <tr>
                            <th className="px-3 py-2">ชื่อวัตถุดิบ/ปุ๋ย/ยา</th>
                            <th className="px-3 py-2">ปริมาณ</th>
                            <th className="px-3 py-2">หน่วย</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100">
                          {application.items && application.items.map((item) => (
                            <tr key={item.id} className="hover:bg-slate-50/50">
                              <td className="px-3 py-2 font-medium text-slate-800">{item.is_masked ? 'ข้อมูลเข้ารหัส' : item.item_name}</td>
                              <td className="px-3 py-2 text-slate-600">{item.is_masked ? 'ข้อมูลเข้ารหัส' : item.quantity}</td>
                              <td className="px-3 py-2 text-slate-600">{item.unit || '-'}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Modal แก้ไขบันทึกการให้ปุ๋ย/ยา */}
      <Modal
        isOpen={isEditModalOpen}
        title="แก้ไขบันทึกการให้ปุ๋ย/ยา"
        onClose={() => setIsEditModalOpen(false)}
      >
        <div className="max-h-[75vh] overflow-y-auto pr-1 space-y-4">
          {editError && (
            <div className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-xs text-rose-600">
              {editError}
            </div>
          )}

          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-600">วันที่</label>
              <ThaiDateInput
                value={editForm.applied_date}
                onChange={(value) => setEditForm((prev) => ({ ...prev, applied_date: value }))}
                className="w-full"
                label="วันที่"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-600">ประเภท</label>
              <AutocompleteInput
                value={editForm.category}
                onChange={(value) => setEditForm((prev) => ({ ...prev, category: value }))}
                placeholder="เช่น ปุ๋ย / ยา"
                onSuggestionSelect={(suggestion) =>
                  setEditForm((prev) => ({ ...prev, category: suggestion.last_category || prev.category }))
                }
              />
            </div>
          </div>

          <div>
            <div className="mb-2 flex items-center justify-between">
              <label className="block text-xs font-medium text-slate-600">รายการผสม</label>
              <button
                type="button"
                onClick={addEditItemRow}
                className="inline-flex items-center gap-1 text-xs font-medium text-farm-700 hover:text-farm-800"
              >
                <Plus size={14} /> เพิ่มรายการ
              </button>
            </div>

            <div className="space-y-2">
              {editForm.items.map((item, idx) => (
                <div key={idx} className="grid grid-cols-[1.6fr_0.8fr_0.9fr_auto] gap-2 items-center rounded-xl border border-slate-200 bg-slate-50 p-2">
                  <AutocompleteInput
                    value={item.item_name}
                    onChange={(val) => updateEditItem(idx, 'item_name', val)}
                    placeholder="ชื่อวัตถุดิบ"
                    onSuggestionSelect={(suggestion) => {
                      updateEditItem(idx, 'item_name', suggestion.item_name);
                      if (suggestion.last_unit) updateEditItem(idx, 'unit', suggestion.last_unit);
                      if (suggestion.last_category) {
                        setEditForm((prev) => ({ ...prev, category: suggestion.last_category }));
                      }
                    }}
                  />
                  <input
                    type="number"
                    min="0"
                    step="0.1"
                    value={item.quantity}
                    onChange={(e) => updateEditItem(idx, 'quantity', Number(e.target.value || 0))}
                    placeholder="ปริมาณ"
                    className="w-full rounded-xl border border-slate-200 bg-white px-2.5 py-2 text-sm text-slate-700 outline-none transition focus:border-farm-500"
                  />
                  <AutocompleteInput
                    value={item.unit}
                    onChange={(val) => updateEditItem(idx, 'unit', val)}
                    placeholder="หน่วย"
                    onSuggestionSelect={(suggestion) => updateEditItem(idx, 'unit', suggestion.last_unit || item.unit)}
                  />
                  <button
                    type="button"
                    onClick={() => removeEditItemRow(idx)}
                    disabled={editForm.items.length === 1}
                    className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-rose-200 bg-rose-50 text-rose-600 transition hover:bg-rose-100 disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    <Trash2 size={14} />
                  </button>
                  <div className="col-span-full">
                    <StockSelect value={item.stock} products={stockItems} onChange={(value) => setEditForm((current) => ({ ...current, items: current.items.map((row, i) => (i === idx ? { ...row, ...stockFields(row, value) } : row)) }))} />
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-slate-600">หมายเหตุ</label>
            <textarea
              value={editForm.note}
              onChange={(e) => setEditForm((prev) => ({ ...prev, note: e.target.value }))}
              rows="2"
              className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 outline-none transition focus:border-farm-500 focus:ring-2 focus:ring-farm-100"
              placeholder="หมายเหตุเพิ่มเติม"
            />
          </div>

          <div className="flex justify-end gap-2 pt-2 border-t border-slate-100">
            <button
              type="button"
              onClick={() => setIsEditModalOpen(false)}
              className="rounded-xl border border-slate-200 px-4 py-2 text-sm font-medium text-slate-600 transition hover:bg-slate-50"
            >
              ยกเลิก
            </button>
            <button
              type="button"
              onClick={submitEditApplication}
              disabled={isSavingEdit}
              className="rounded-xl bg-farm-700 px-4 py-2 text-sm font-semibold text-white shadow-soft transition hover:bg-farm-800 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {isSavingEdit ? 'กำลังบันทึก...' : 'บันทึกการแก้ไข'}
            </button>
          </div>
        </div>
      </Modal>
    </div>
  );
}

export default PlotDetail;
