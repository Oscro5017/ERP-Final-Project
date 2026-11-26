import { useCallback, useEffect, useState } from 'react';
import { ClipboardList, Pencil, Plus, Sprout, Trash2, Truck } from 'lucide-react';
import { useAutomation } from '../../components/AutomationPrompt';
import Modal from '../../components/Modal';
import PlantingPrompt from '../../components/PlantingPrompt';
import SearchSelect from '../../components/SearchSelect';
import StockDocumentForm from '../../components/StockDocumentForm';
import ThaiDateInput from '../../components/ThaiDateInput';
import { api, getRole } from '../../lib/api';
import { fetchAll } from '../../lib/lookups';
import { formatThaiDate } from '../../utils/dateUtils';
import { CATEGORY_LABELS, itemName, partnerName } from '../../utils/itemCategories';
import { formatNumber } from '../../utils/format';
import { MASKED_NUMBER, MASKED_TEXT } from '../../utils/masking';
import { useDialog } from '../../components/DialogProvider';

const PAGE_LIMIT = 20;
const inputClass = 'w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm';
const emptyLine = () => ({ product_id: '', quantity: '', unit: '', delivery_date: '', unit_price: '' });
const emptyForm = () => ({ customer_id: '', safety_days: '0', delivery_location: '', note: '', auto_planting: true, lines: [emptyLine()] });

const plantingLabels = {
  unmapped: ['ยังไม่ผูกพันธุ์ผัก', 'bg-amber-50 text-amber-700'],
  not_required: ['ไม่ต้องปลูก', 'bg-slate-100 text-slate-600'],
  waiting: ['รอเพาะ', 'bg-sky-50 text-sky-700'],
  late: ['เลยกำหนดเพาะ', 'bg-rose-50 text-rose-700'],
  ready: ['รอสร้างรอบปลูก', 'bg-amber-50 text-amber-700'],
  planted: ['สร้างรอบปลูกแล้ว', 'bg-emerald-50 text-emerald-700'],
  covered: ['ของพอ ไม่ต้องปลูก', 'bg-emerald-50 text-emerald-700'],
  manual: ['วางแผนเอง', 'bg-slate-100 text-slate-600'],
  delivered: ['ส่งครบแล้ว', 'bg-slate-100 text-slate-600'],
};
const statusLabels = { open: 'เปิดอยู่', delivered: 'ส่งแล้ว', cancelled: 'ยกเลิก' };

function Orders() {
  const { confirm } = useDialog();
  const isOwner = getRole() === 'owner';
  const [orders, setOrders] = useState([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [filter, setFilter] = useState('open');
  const [customers, setCustomers] = useState([]);
  const [products, setProducts] = useState([]);
  const [cropTypes, setCropTypes] = useState([]);
  const [form, setForm] = useState(emptyForm);
  const [editingId, setEditingId] = useState(null);
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [message, setMessage] = useState('');
  const [formError, setFormError] = useState('');
  const [plantingLineId, setPlantingLineId] = useState(null);
  const [deliveryOrderId, setDeliveryOrderId] = useState(null);
  const [showAllItems, setShowAllItems] = useState(false);
  const { ask } = useAutomation();

  const loadOrders = useCallback(async () => {
    setIsLoading(true);
    try {
      const params = new URLSearchParams({ limit: PAGE_LIMIT, offset });
      if (filter !== 'all') params.set('status', filter);
      const data = await api(`/sales-orders?${params}`);
      setOrders(data.items);
      setTotal(data.total);
    } catch (error) {
      setMessage(error.message);
    } finally {
      setIsLoading(false);
    }
  }, [filter, offset]);

  useEffect(() => { loadOrders(); }, [loadOrders]);

  useEffect(() => {
    Promise.all([api('/customers'), fetchAll('/products'), api('/crop-types')])
      .then(([customerData, productData, cropData]) => {
        setCustomers(customerData?.items || customerData);
        setProducts(productData.filter((product) => product.is_active !== false));
        setCropTypes(cropData);
      })
      .catch((error) => setMessage(error.message));
  }, []);

  const setLine = (index, changes) => setForm((current) => ({
    ...current,
    lines: current.lines.map((line, i) => (i === index ? { ...line, ...changes } : line)),
  }));

  const pickProduct = (index, productId) => {
    const product = products.find((item) => String(item.id) === productId);
    setLine(index, { product_id: productId, unit: product?.unit || '' });
  };

  const openCreate = () => {
    setEditingId(null);
    setForm(emptyForm());
    setFormError('');
    setIsFormOpen(true);
  };

  const openEdit = (order) => {
    setEditingId(order.id);
    setForm({
      customer_id: String(order.customer_id),
      safety_days: String(order.safety_days),
      delivery_location: order.delivery_location || '',
      note: order.note || '',
      auto_planting: order.auto_planting,
      lines: order.lines.map((line) => ({
        id: line.id, product_id: String(line.product_id), quantity: String(line.quantity), unit: line.unit, delivery_date: line.delivery_date,
        unit_price: line.unit_price ?? '',
      })),
    });
    setFormError('');
    setIsFormOpen(true);
  };

  const save = async (event) => {
    event.preventDefault();
    if (!form.customer_id) return setFormError('กรุณาเลือกลูกค้า');
    const incomplete = form.lines.findIndex((line) => !line.product_id || !line.delivery_date);
    if (incomplete >= 0) return setFormError(`รายการที่ ${incomplete + 1}: กรุณาเลือกสินค้าและวันส่ง`);
    let autoPlanting = form.auto_planting;
    const canPlant = form.lines.some((line) => products.find((product) => String(product.id) === line.product_id)?.category === 'vegetable');
    if (!editingId && canPlant) {
      const mode = await ask('order_planting', `ออเดอร์มี ${form.lines.length} รายการ`);
      if (!mode) return undefined;
      autoPlanting = mode === 'auto';
    }
    setIsSaving(true);
    setFormError('');
    const payload = {
      customer_id: Number(form.customer_id),
      safety_days: Number(form.safety_days || 0),
      delivery_location: form.delivery_location.trim() || null,
      note: form.note.trim() || null,
      auto_planting: autoPlanting,
      lines: form.lines.map((line) => ({
        ...(line.id ? { id: line.id } : {}),
        product_id: Number(line.product_id), quantity: line.quantity, unit: line.unit || null, delivery_date: line.delivery_date,
        unit_price: line.unit_price === '' ? null : line.unit_price,
      })),
    };
    try {
      await api(editingId ? `/sales-orders/${editingId}` : '/sales-orders', {
        method: editingId ? 'PATCH' : 'POST', body: JSON.stringify(payload),
      });
      setIsFormOpen(false);
      setMessage(autoPlanting ? 'บันทึกออเดอร์และวางแผนเพาะแล้ว' : 'บันทึกออเดอร์แล้ว ไม่ได้สร้างกิจกรรมเพาะ');
      await loadOrders();
    } catch (error) {
      setFormError(error.message);
    } finally {
      setIsSaving(false);
    }
    return undefined;
  };

  const addCustomer = async (name) => {
    try {
      const created = await api('/customers', { method: 'POST', body: JSON.stringify({ name }) });
      setCustomers((current) => [...current, created]);
      setForm((current) => ({ ...current, customer_id: String(created.id) }));
    } catch (error) {
      setFormError(error.message);
    }
  };

  const closeOrder = async (order, status) => {
    const question = status === 'delivered' ? 'ปิดออเดอร์โดยไม่ตัดสต็อก' : 'ยกเลิกออเดอร์';
    if (!await confirm(`${question} ${order.order_no}? กิจกรรมเพาะที่ยังค้างจะถูกลบ และเปิดกลับไม่ได้`)) return;
    try {
      await api(`/sales-orders/${order.id}/close`, { method: 'POST', body: JSON.stringify({ status }) });
      setMessage(`${question}แล้ว`);
      await loadOrders();
    } catch (error) {
      setMessage(error.message);
    }
  };

  const mapCrop = async (cropTypeId, productId) => {
    if (!cropTypeId) return;
    try {
      await api(`/crop-types/${cropTypeId}/product-mapping`, { method: 'PATCH', body: JSON.stringify({ product_id: productId }) });
      setCropTypes(await api('/crop-types'));
      setMessage('ผูกพันธุ์ผักและคำนวณวันเพาะแล้ว');
      await loadOrders();
    } catch (error) {
      setMessage(error.message);
    }
  };

  const unmappedCrops = cropTypes.filter((crop) => !crop.product_id);

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-slate-800">ออเดอร์ลูกค้า</h1>
          <p className="mt-1 text-sm text-slate-500">บันทึกสินค้า ปริมาณ และวันส่ง ระบบคำนวณวันเพาะช้าที่สุดให้</p>
        </div>
        <button type="button" onClick={openCreate} className="inline-flex items-center justify-center gap-2 rounded-xl bg-farm-700 px-4 py-2.5 text-sm font-semibold text-white"><Plus size={16} /> เพิ่มออเดอร์</button>
      </div>

      {message && <p role="status" className="rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600">{message}</p>}

      <div className="inline-flex gap-1 rounded-xl bg-slate-100 p-1" aria-label="กรองสถานะออเดอร์">
        {[['open', 'เปิดอยู่'], ['delivered', 'ส่งแล้ว'], ['cancelled', 'ยกเลิก'], ['all', 'ทั้งหมด']].map(([value, label]) => (
          <button key={value} type="button" onClick={() => { setOffset(0); setFilter(value); }} className={`rounded-lg px-3 py-1.5 text-xs font-medium ${filter === value ? 'bg-white text-farm-800 shadow-sm' : 'text-slate-500'}`}>{label}</button>
        ))}
      </div>

      {isLoading ? <p className="p-8 text-center text-sm text-slate-500">กำลังโหลดออเดอร์…</p> : orders.length === 0 ? (
        <div className="rounded-2xl border border-slate-200 bg-white p-10 text-center text-sm text-slate-500"><ClipboardList className="mx-auto mb-2" />ไม่มีออเดอร์ในรายการนี้</div>
      ) : orders.map((order) => (
        <article key={order.id} className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-soft">
          <div className="flex flex-col gap-3 border-b border-slate-100 p-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h2 className="font-semibold text-slate-800">{order.order_no} · {order.is_masked ? MASKED_TEXT : order.customer_name}</h2>
              <p className="text-xs text-slate-500">
                สั่ง {formatThaiDate(order.order_date)} · {statusLabels[order.status]}
                {order.safety_days > 0 && ` · เผื่อ ${order.safety_days} วัน`}
                {order.delivery_location && !order.is_masked && ` · ส่งที่ ${order.delivery_location}`}
              </p>
              {order.note && !order.is_masked && <p className="mt-1 text-xs text-slate-500">{order.note}</p>}
              {order.decrypt_failed && <p className="mt-1 text-xs text-rose-600">ถอดรหัสข้อมูลบางส่วนไม่สำเร็จ</p>}
            </div>
            {order.status === 'open' && (
              <div className="flex flex-wrap gap-2 text-sm">
                {isOwner && <button type="button" onClick={() => openEdit(order)} className="inline-flex items-center gap-1 rounded-lg border border-slate-200 px-3 py-1.5"><Pencil size={14} /> แก้ไข</button>}
                <button type="button" onClick={() => setDeliveryOrderId(order.id)} className="inline-flex items-center gap-1 rounded-lg border border-emerald-200 px-3 py-1.5 text-emerald-700"><Truck size={14} /> ส่งของ</button>
                <button type="button" onClick={() => closeOrder(order, 'delivered')} className="rounded-lg border border-slate-200 px-3 py-1.5 text-slate-600">ปิดออเดอร์</button>
                <button type="button" onClick={() => closeOrder(order, 'cancelled')} className="rounded-lg border border-rose-200 px-3 py-1.5 text-rose-600">ยกเลิก</button>
              </div>
            )}
          </div>
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead className="bg-slate-50 text-slate-600">
                <tr>{['สินค้า', 'ปริมาณ', 'ราคา', 'วันส่ง', 'มีของ', 'ต้องปลูก', 'เพาะช้าที่สุด', 'โต๊ะโดยประมาณ', 'การปลูก'].map((head) => <th key={head} className="whitespace-nowrap px-4 py-2 font-semibold">{head}</th>)}</tr>
              </thead>
              <tbody>
                {order.lines.map((line) => {
                  const [label, color] = plantingLabels[line.planting_status];
                  return (
                    <tr key={line.id} className="border-t border-slate-100">
                      <td className="px-4 py-3 font-medium text-slate-800">{order.is_masked ? (line.crop_name || 'สินค้า (ปิดบัง)') : line.product_name}</td>
                      <td className="whitespace-nowrap px-4 py-3">{line.quantity} {line.unit}{line.delivered_quantity > 0 && <span className="block text-xs text-slate-500">ส่งแล้ว {line.delivered_quantity}</span>}</td>
                      <td className="whitespace-nowrap px-4 py-3">{!line.has_price ? '-' : order.is_masked ? MASKED_NUMBER : `${formatNumber(line.unit_price)}/${line.unit}`}</td>
                      <td className="whitespace-nowrap px-4 py-3">{formatThaiDate(line.delivery_date)}</td>
                      <td className="whitespace-nowrap px-4 py-3 text-xs">คลัง {line.from_stock}<span className="block">กำลังปลูก {line.from_growing}</span></td>
                      <td className="whitespace-nowrap px-4 py-3">{line.crop_name ? line.to_plant : '-'}</td>
                      <td className="whitespace-nowrap px-4 py-3">{line.latest_sow_date ? formatThaiDate(line.latest_sow_date) : '-'}</td>
                      <td className="px-4 py-3">{line.tables_needed ?? '-'}</td>
                      <td className="px-4 py-3">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className={`whitespace-nowrap rounded-full px-2.5 py-1 text-xs font-semibold ${color}`}>{label}</span>
                          {order.status === 'open' && line.planting_ready && line.to_plant > 0 && (
                            <button type="button" onClick={() => setPlantingLineId(line.id)} className="inline-flex items-center gap-1 whitespace-nowrap text-xs font-semibold text-farm-700"><Sprout size={14} /> สร้างรอบปลูก</button>
                          )}
                          {order.status === 'open' && line.planting_status === 'unmapped' && (
                            <select value="" aria-label="เลือกพันธุ์ผัก" onChange={(event) => mapCrop(event.target.value, line.product_id)} className="rounded-lg border border-slate-200 bg-white px-2 py-1 text-xs">
                              <option value="">เลือกพันธุ์ผัก</option>
                              {unmappedCrops.map((crop) => <option key={crop.id} value={crop.id}>{crop.name}</option>)}
                            </select>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </article>
      ))}

      {total > PAGE_LIMIT && (
        <div className="flex items-center justify-between text-sm text-slate-600">
          <span>ทั้งหมด {total} ออเดอร์</span>
          <div className="flex gap-2">
            <button type="button" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_LIMIT))} className="rounded-lg border px-3 py-1.5 disabled:opacity-40">ก่อนหน้า</button>
            <button type="button" disabled={offset + PAGE_LIMIT >= total} onClick={() => setOffset(offset + PAGE_LIMIT)} className="rounded-lg border px-3 py-1.5 disabled:opacity-40">ถัดไป</button>
          </div>
        </div>
      )}

      <Modal isOpen={isFormOpen} title={editingId ? 'แก้ไขออเดอร์' : 'เพิ่มออเดอร์'} onClose={() => !isSaving && setIsFormOpen(false)}>
        <form onSubmit={save} className="max-h-[70vh] space-y-4 overflow-y-auto text-sm">
          <SearchSelect label="ลูกค้า" value={form.customer_id} onChange={(value) => setForm({ ...form, customer_id: value })} placeholder="พิมพ์ชื่อหรือเลือก" options={customers.map((customer) => ({ value: customer.id, label: partnerName(customer, 'ลูกค้า') }))} onCreate={addCustomer} createLabel="เพิ่มลูกค้า" />
          {form.lines.map((line, index) => (
            <fieldset key={line.id || `new-${index}`} className="space-y-2 rounded-xl border border-slate-200 p-3">
              <div className="flex items-center justify-between">
                <span className="font-medium">รายการที่ {index + 1}</span>
                {form.lines.length > 1 && <button type="button" aria-label={`ลบรายการที่ ${index + 1}`} onClick={() => setForm({ ...form, lines: form.lines.filter((_, i) => i !== index) })} className="p-1 text-rose-500"><Trash2 size={15} /></button>}
              </div>
              <SearchSelect
                label="สินค้า"
                value={line.product_id}
                onChange={(value) => pickProduct(index, value)}
                placeholder="พิมพ์ชื่อหรือเลือก"
                options={products
                  .filter((product) => showAllItems || product.category === 'vegetable' || String(product.id) === line.product_id)
                  .map((product) => ({ value: product.id, label: itemName(product), hint: CATEGORY_LABELS[product.category] }))}
              />
              <div className="grid grid-cols-2 gap-2">
                <div className="flex items-center gap-2">
                  <input required type="number" min="0.001" step="0.001" aria-label="ปริมาณ" placeholder="ปริมาณ" value={line.quantity} onChange={(event) => setLine(index, { quantity: event.target.value })} className={inputClass} />
                  <span className="whitespace-nowrap text-slate-500">{line.unit}</span>
                </div>
                <input type="number" min="0" step="0.01" aria-label="ราคาต่อหน่วย" placeholder={`ราคาต่อ ${line.unit || 'หน่วย'} (ไม่บังคับ)`} value={line.unit_price} onChange={(event) => setLine(index, { unit_price: event.target.value })} className={inputClass} />
                <div className="col-span-2"><ThaiDateInput value={line.delivery_date} onChange={(value) => setLine(index, { delivery_date: value })} required label="วันส่ง" /></div>
              </div>
            </fieldset>
          ))}
          <button type="button" onClick={() => setForm({ ...form, lines: [...form.lines, emptyLine()] })} className="inline-flex items-center gap-1 font-semibold text-farm-700"><Plus size={15} /> เพิ่มรายการ</button>
          <label className="flex items-center gap-2 text-xs text-slate-600"><input type="checkbox" checked={showAllItems} onChange={(event) => setShowAllItems(event.target.checked)} /> แสดงของทุกประเภท</label>
          {editingId && <label className="flex items-center gap-2"><input type="checkbox" checked={form.auto_planting} onChange={(event) => setForm({ ...form, auto_planting: event.target.checked })} /> ให้ระบบสร้างกิจกรรมเพาะ</label>}
          <label className="block">เผื่อเวลาก่อนวันส่ง (วัน)
            <input type="number" min="0" max="60" value={form.safety_days} onChange={(event) => setForm({ ...form, safety_days: event.target.value })} className={inputClass} />
          </label>
          <label className="block">สถานที่ส่ง
            <input maxLength={500} value={form.delivery_location} onChange={(event) => setForm({ ...form, delivery_location: event.target.value })} className={inputClass} />
          </label>
          <label className="block">หมายเหตุ
            <input maxLength={1000} value={form.note} onChange={(event) => setForm({ ...form, note: event.target.value })} className={inputClass} />
          </label>
          {formError && <p role="alert" className="rounded-xl bg-rose-50 p-3 text-rose-700">{formError}</p>}
          <button disabled={isSaving} className="w-full rounded-xl bg-farm-700 px-4 py-2.5 font-semibold text-white disabled:opacity-50">{isSaving ? 'กำลังบันทึก…' : 'บันทึกออเดอร์'}</button>
        </form>
      </Modal>

      <StockDocumentForm
        docType={deliveryOrderId ? 'outbound' : null}
        initialOrderId={deliveryOrderId}
        onClose={() => setDeliveryOrderId(null)}
        onSaved={(text) => { setDeliveryOrderId(null); setMessage(text); loadOrders(); }}
      />

      <PlantingPrompt
        lineId={plantingLineId}
        onClose={() => setPlantingLineId(null)}
        onCreated={(count) => { setPlantingLineId(null); setMessage(`สร้างรอบปลูก ${count} รอบแล้ว`); loadOrders(); }}
      />
    </div>
  );
}

export default Orders;
