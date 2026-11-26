import { useEffect, useState } from 'react';
import { Plus, Trash2 } from 'lucide-react';
import { useAutomation } from './AutomationPrompt';
import Modal from './Modal';
import SearchSelect from './SearchSelect';
import ThaiDateInput from './ThaiDateInput';
import { api, getRole } from '../lib/api';
import { fetchAll } from '../lib/lookups';
import { formatThaiDate, getLocalDateString } from '../utils/dateUtils';
import { CATEGORY_LABELS, cycleName, itemName, partnerName } from '../utils/itemCategories';
import { formatStockWarning } from '../utils/stockWarnings';
import { compatibleUnits, convert } from '../utils/units';

const inputClass = 'w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm';
const PURPOSES = [['sale', 'ส่งขาย'], ['order', 'ส่งตามออเดอร์'], ['other', 'อื่น ๆ']];
let nextKey = 0;
const emptyLine = () => ({ key: nextKey += 1, product_id: '', quantity: '', unit: '', unit_price: '' });
const emptyForm = (purpose) => ({
  purpose, order_id: '', doc_date: getLocalDateString(), partner_id: '', crop_cycle_id: '',
  reference_no: '', note: '', record_other: false, lines: [emptyLine()],
});
const money = (value) => value.toLocaleString('th-TH', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const round = (value) => Number(value.toFixed(3));

/** Receive stock, or send it out as a sale, an order delivery or something else. */
function StockDocumentForm({ docType, initialPurpose = 'sale', initialOrderId = null, onClose, onSaved }) {
  const isOwner = getRole() === 'owner';
  const isInbound = docType === 'inbound';
  const { ask } = useAutomation();
  const [data, setData] = useState(null);
  const [form, setForm] = useState(() => emptyForm(initialPurpose));
  const [showAllItems, setShowAllItems] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState('');

  const update = (changes) => setForm((current) => ({ ...current, ...changes }));
  const isOrder = !isInbound && form.purpose === 'order';

  useEffect(() => {
    let ignore = false;
    setData(null);
    setError('');
    setForm(emptyForm(initialOrderId ? 'order' : initialPurpose));
    setShowAllItems(false);
    if (!docType) return undefined;
    Promise.all([
      fetchAll('/products'),
      docType === 'inbound' ? fetchAll('/suppliers') : api('/customers'),
      api('/crop-cycles'),
      api(`/trade/last-prices?doc_type=${docType}`),
      docType === 'inbound' ? [] : fetchAll('/sales-orders?status=open'),
    ]).then(([products, partners, cycles, prices, orders]) => {
      if (ignore) return;
      const loaded = { products: products.filter((item) => item.is_active !== false), partners, cycles, prices, orders };
      setData(loaded);
      if (initialOrderId) pickOrder(String(initialOrderId), loaded);
    }).catch((err) => { if (!ignore) setError(err.message); });
    return () => { ignore = true; };
    // The form starts over each time it is opened.
  }, [docType, initialPurpose, initialOrderId]);

  const productOf = (id, source = data) => source?.products.find((item) => String(item.id) === String(id));
  const orderOf = (id, source = data) => source?.orders.find((item) => String(item.id) === String(id));
  const lastPrice = (productId, unit, source = data) => source?.prices.find(
    (price) => String(price.product_id) === String(productId) && price.unit === unit,
  )?.unit_price;

  const leftOf = (line) => round(line.quantity - line.delivered_quantity);

  const pickOrder = async (orderId, source = data) => {
    if (!orderId) {
      update({ order_id: '', partner_id: '', lines: [] });
      return;
    }
    const order = orderOf(orderId, source);
    if (!order) {
      setError('ไม่พบออเดอร์ที่เปิดอยู่');
      return;
    }
    const open = order.lines.filter((line) => leftOf(line) > 0);
    const mode = await ask('order_fill', `${order.order_no} มีรายการค้างส่ง ${open.length} รายการ`);
    if (!mode) return;
    setError('');
    update({
      purpose: 'order',
      order_id: orderId,
      partner_id: String(order.customer_id),
      lines: open.map((line) => {
        const left = leftOf(line);
        const agreed = isOwner ? line.unit_price : null;
        const price = mode === 'auto' ? agreed ?? lastPrice(line.product_id, line.unit, source) ?? '' : '';
        return {
          key: nextKey += 1,
          line_id: line.id,
          product_id: String(line.product_id),
          unit: line.unit,
          left,
          has_price: line.has_price,
          use_order_price: mode === 'auto' && line.has_price && !isOwner,
          crop_name: line.crop_name,
          product_name: line.product_name,
          quantity: mode === 'auto' ? String(left) : '',
          unit_price: String(price),
        };
      }),
    });
  };

  const pickPurpose = (purpose) => {
    setError('');
    update({ purpose, order_id: '', partner_id: '', lines: purpose === 'order' ? [] : [emptyLine()] });
  };

  const setLine = (index, changes) => setForm((current) => ({
    ...current, lines: current.lines.map((line, i) => (i === index ? { ...line, ...changes } : line)),
  }));

  const suggestedPrice = (productId, unit) => {
    const isSale = isInbound || form.purpose === 'sale';
    return isSale ? String(lastPrice(productId, unit) ?? '') : '';
  };

  const pickUnit = (index, unit) => {
    const line = form.lines[index];
    const perUnit = convert(1, unit, line.unit);
    const converted = line.unit_price === '' || perUnit === null ? NaN : Number(line.unit_price) * perUnit;
    // Prices are stored to the satang, so keep a converted price only when nothing is rounded away.
    const isExact = Math.abs(converted * 100 - Math.round(converted * 100)) < 1e-6;
    setLine(index, { unit, unit_price: isExact ? String(Number(converted.toFixed(2))) : suggestedPrice(line.product_id, unit) });
  };

  const pickItem = (index, productId) => {
    const unit = productOf(productId)?.unit || '';
    setLine(index, { product_id: productId, unit, unit_price: suggestedPrice(productId, unit) });
  };

  const addPartner = async (name) => {
    try {
      const created = await api(isInbound ? '/suppliers' : '/customers', { method: 'POST', body: JSON.stringify({ name }) });
      setData((current) => ({ ...current, partners: [...current.partners, created] }));
      update({ partner_id: String(created.id) });
    } catch (err) {
      setError(err.message);
    }
  };

  const total = form.lines.reduce((sum, line) => (
    line.unit_price === '' ? sum : sum + Number(line.quantity || 0) * Number(line.unit_price)
  ), 0);
  const usesHiddenPrice = isOrder && form.lines.some((line) => line.use_order_price && Number(line.quantity) > 0);

  const stockAfter = (line) => {
    const product = productOf(line.product_id);
    if (!product || !Number(line.quantity)) return null;
    // Other lines of this document can use the same item.
    const change = form.lines
      .filter((other) => other.product_id === line.product_id)
      .reduce((sum, other) => sum + (convert(Number(other.quantity || 0), other.unit, product.unit) ?? NaN), 0);
    const after = product.on_hand + (isInbound ? change : -change);
    return Number.isFinite(after) ? { before: product.on_hand, after: round(after), unit: product.unit } : null;
  };

  const save = async (event) => {
    event.preventDefault();
    const lines = isOrder ? form.lines.filter((line) => Number(line.quantity) > 0) : form.lines;
    if (isOrder && !form.order_id) return setError('กรุณาเลือกออเดอร์');
    if (!lines.length) return setError('กรุณาระบุปริมาณอย่างน้อย 1 รายการ');
    const missing = lines.findIndex((line) => !line.product_id || !(Number(line.quantity) > 0));
    if (missing >= 0) return setError(`รายการที่ ${missing + 1}: กรุณาเลือกของและระบุจำนวนมากกว่า 0`);
    if (!isInbound && form.purpose === 'other' && !form.note.trim()) return setError('กรุณาระบุเหตุผลที่ส่งออก');

    let recordFinance = false;
    let closeWhenComplete = false;
    if (!isInbound && form.purpose === 'other') {
      recordFinance = form.record_other;
    } else if (total > 0 || usesHiddenPrice) {
      const detail = total > 0 && !usesHiddenPrice ? `ยอดรวม ${money(total)} บาท` : 'ยอดตามราคาที่ตกลงในออเดอร์';
      const mode = await ask(isInbound ? 'inbound_finance' : 'outbound_finance', detail);
      if (!mode) return undefined;
      recordFinance = mode === 'auto';
    }
    if (isOrder) {
      const sent = new Map(lines.map((line) => [line.line_id, Number(line.quantity)]));
      const order = orderOf(form.order_id);
      if (order.lines.every((line) => leftOf(line) - (sent.get(line.id) || 0) <= 0)) {
        const mode = await ask('order_close', `${order.order_no} จะส่งครบทุกรายการ`);
        if (!mode) return undefined;
        closeWhenComplete = mode === 'auto';
      }
    }

    const price = (line) => (line.unit_price === '' ? null : line.unit_price);
    setIsSaving(true);
    setError('');
    try {
      let docNo;
      let warnings;
      if (isOrder) {
        const result = await api(`/sales-orders/${form.order_id}/deliver`, {
          method: 'POST',
          body: JSON.stringify({
            doc_date: form.doc_date, note: form.note.trim() || null,
            record_finance: recordFinance, close_when_complete: closeWhenComplete,
            lines: lines.map((line) => ({
              line_id: line.line_id, quantity: line.quantity, unit_price: price(line), use_order_price: line.use_order_price,
            })),
          }),
        });
        docNo = result.doc_no;
        warnings = result.warnings;
      } else {
        const result = await api(`/trade/${docType}`, {
          method: 'POST',
          body: JSON.stringify({
            doc_date: form.doc_date,
            [isInbound ? 'supplier_id' : 'customer_id']: form.partner_id ? Number(form.partner_id) : null,
            crop_cycle_id: form.crop_cycle_id ? Number(form.crop_cycle_id) : null,
            reference_no: form.reference_no.trim() || null,
            note: form.note.trim() || null,
            record_finance: recordFinance,
            ...(isInbound ? {} : { purpose: form.purpose }),
            lines: lines.map((line) => ({
              product_id: Number(line.product_id), quantity: line.quantity, unit: line.unit, unit_price: price(line),
            })),
          }),
        });
        docNo = result.doc_no;
        warnings = result.warnings;
      }
      const names = Object.fromEntries(data.products.map((item) => [item.id, itemName(item)]));
      const alerts = warnings.map((warning) => formatStockWarning(warning, names)).join(', ');
      const finance = (total > 0 || usesHiddenPrice) && !recordFinance ? ' · ยังไม่ลงบัญชี' : '';
      onSaved(`บันทึกเอกสาร ${docNo} แล้ว${finance}${alerts ? ` · คำเตือน: ${alerts}` : ''}`);
    } catch (err) {
      setError(err.message);
    } finally {
      setIsSaving(false);
    }
    return undefined;
  };

  const sellable = (item) => isInbound || showAllItems || form.purpose === 'other' || item.category === 'vegetable';
  const itemOptions = (selectedId) => (data?.products || [])
    .filter((item) => sellable(item) || String(item.id) === selectedId)
    .map((item) => ({ value: item.id, label: itemName(item), hint: `${CATEGORY_LABELS[item.category]} · เหลือ ${round(item.on_hand)} ${item.unit}` }));
  const partnerKind = isInbound ? 'ซัพพลายเออร์' : 'ลูกค้า';

  return (
    <Modal wide isOpen={Boolean(docType)} title={isInbound ? 'รับของเข้าคลัง' : 'ส่งของออกจากคลัง'} onClose={() => !isSaving && onClose()}>
      <form onSubmit={save} className="max-h-[75vh] space-y-4 overflow-y-auto pr-1 text-sm">
        {!data && !error && <p className="p-6 text-center text-slate-500">กำลังโหลด…</p>}
        {data && (
          <>
            {!isInbound && (
              <div role="radiogroup" aria-label="ประเภทการส่งออก" className="grid grid-cols-3 gap-1 rounded-xl bg-slate-100 p-1">
                {PURPOSES.map(([value, label]) => (
                  <button key={value} type="button" role="radio" aria-checked={form.purpose === value} onClick={() => form.purpose !== value && pickPurpose(value)} className={`rounded-lg px-2 py-2 text-sm font-medium ${form.purpose === value ? 'bg-white text-farm-800 shadow-sm' : 'text-slate-500'}`}>{label}</button>
                ))}
              </div>
            )}

            {isOrder && (
              <SearchSelect
                label="ออเดอร์"
                value={form.order_id}
                onChange={(value) => pickOrder(value)}
                placeholder={data.orders.length ? 'เลือกออเดอร์ที่จะส่ง' : 'ไม่มีออเดอร์ที่เปิดอยู่'}
                options={data.orders.map((order) => ({
                  value: order.id,
                  label: `${order.order_no} · ${order.is_masked ? 'ลูกค้า (ปิดบัง)' : order.customer_name}`,
                  hint: `ส่ง ${formatThaiDate(order.lines.map((line) => line.delivery_date).sort()[0])}`,
                }))}
              />
            )}

            <div className="grid gap-3 sm:grid-cols-2">
              <div><p className="mb-1 text-xs font-medium text-slate-600">วันที่</p><ThaiDateInput value={form.doc_date} onChange={(value) => update({ doc_date: value })} required label="วันที่เอกสาร" /></div>
              {!isOrder && (
                <SearchSelect
                  label={partnerKind}
                  value={form.partner_id}
                  onChange={(value) => update({ partner_id: value })}
                  placeholder="ไม่ระบุ"
                  options={data.partners.map((partner) => ({ value: partner.id, label: partnerName(partner, partnerKind) }))}
                  onCreate={isOwner ? addPartner : undefined}
                  createLabel={`เพิ่ม${partnerKind}`}
                />
              )}
              {!isOrder && (
                <>
                  <SearchSelect label="รอบปลูก" value={form.crop_cycle_id} onChange={(value) => update({ crop_cycle_id: value })} placeholder="ไม่ระบุ" options={data.cycles.map((cycle) => ({ value: cycle.id, label: cycleName(cycle) }))} />
                  <label className="block text-xs font-medium text-slate-600">เลขที่อ้างอิง<input maxLength={120} value={form.reference_no} onChange={(event) => update({ reference_no: event.target.value })} placeholder="เช่น INV-001" className={`mt-1 font-normal ${inputClass}`} /></label>
                </>
              )}
            </div>

            {form.lines.map((line, index) => {
              const product = productOf(line.product_id);
              const stock = stockAfter(line);
              return (
                <fieldset key={line.key} className="space-y-2 rounded-xl border border-slate-200 bg-slate-50/60 p-3">
                  <div className="flex items-center justify-between text-xs font-medium text-slate-500">
                    {isOrder
                      ? <span className="text-sm text-slate-800">{product ? itemName(product) : line.crop_name || line.product_name} · ค้างส่ง {line.left} {line.unit}</span>
                      : <span>รายการที่ {index + 1}</span>}
                    {!isOrder && form.lines.length > 1 && <button type="button" aria-label={`ลบรายการที่ ${index + 1}`} onClick={() => update({ lines: form.lines.filter((_, i) => i !== index) })} className="p-1 text-rose-500"><Trash2 size={15} /></button>}
                  </div>
                  {!isOrder && <SearchSelect label="ของ" value={line.product_id} onChange={(value) => pickItem(index, value)} placeholder="พิมพ์ชื่อหรือเลือก" options={itemOptions(line.product_id)} />}
                  <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                    <label className="text-xs text-slate-600">จำนวน<input type="number" min={isOrder ? '0' : '0.001'} max={isOrder ? line.left : undefined} step="0.001" value={line.quantity} onChange={(event) => setLine(index, { quantity: event.target.value })} className={`mt-1 ${inputClass}`} /></label>
                    <label className="text-xs text-slate-600">หน่วย
                      <select disabled={isOrder || !product} value={line.unit} onChange={(event) => pickUnit(index, event.target.value)} className={`mt-1 disabled:bg-slate-100 ${inputClass}`}>
                        {(isOrder || !product ? [line.unit] : compatibleUnits(product.unit)).map((unit) => <option key={unit} value={unit}>{unit || '-'}</option>)}
                      </select>
                    </label>
                    <label className="text-xs text-slate-600">ราคาต่อหน่วย (บาท)<input type="number" min="0" step="0.01" value={line.unit_price} onChange={(event) => setLine(index, { unit_price: event.target.value })} placeholder={line.use_order_price ? 'ตามออเดอร์' : 'ไม่ระบุ'} className={`mt-1 ${inputClass}`} /></label>
                  </div>
                  {stock && <p className={`text-xs ${stock.after < 0 ? 'font-medium text-rose-600' : 'text-slate-500'}`}>คงเหลือ {round(stock.before)} → {stock.after} {stock.unit}{stock.after < 0 && ' (ไม่พอ)'}{isOrder && ` · ค้างส่งหลังจากนี้ ${round(line.left - Number(line.quantity))} ${line.unit}`}</p>}
                </fieldset>
              );
            })}

            {!isOrder && (
              <div className="flex flex-wrap items-center justify-between gap-2">
                <button type="button" onClick={() => update({ lines: [...form.lines, emptyLine()] })} className="inline-flex items-center gap-1 font-semibold text-farm-700"><Plus size={15} /> เพิ่มรายการ</button>
                {!isInbound && form.purpose === 'sale' && <label className="flex items-center gap-2 text-xs text-slate-600"><input type="checkbox" checked={showAllItems} onChange={(event) => setShowAllItems(event.target.checked)} /> แสดงของทุกประเภท</label>}
              </div>
            )}

            <label className="block text-xs font-medium text-slate-600">{!isInbound && form.purpose === 'other' ? 'เหตุผล (จำเป็น)' : 'หมายเหตุ'}
              <textarea rows={2} maxLength={500} value={form.note} onChange={(event) => update({ note: event.target.value })} placeholder={!isInbound && form.purpose === 'other' ? 'เช่น แจก ตัวอย่าง คืนของ ใช้ภายในฟาร์ม' : ''} className={`mt-1 font-normal ${inputClass}`} />
            </label>
            {!isInbound && form.purpose === 'other' && (
              <label className="flex items-center gap-2 text-slate-600"><input type="checkbox" checked={form.record_other} onChange={(event) => update({ record_other: event.target.checked })} /> ลงรายรับจากรายการนี้ (ต้องใส่ราคา)</label>
            )}
          </>
        )}

        {error && <p role="alert" className="rounded-xl bg-rose-50 p-3 text-rose-700">{error}</p>}
        {data && (
          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 pt-3">
            <span className="font-semibold text-slate-800">{usesHiddenPrice ? 'ยอดรวมตามราคาในออเดอร์' : `ยอดรวม ${money(total)} บาท`}</span>
            <button disabled={isSaving} className="rounded-xl bg-farm-700 px-5 py-2.5 font-semibold text-white disabled:opacity-50">{isSaving ? 'กำลังบันทึก…' : isInbound ? 'บันทึกและรับเข้าคลัง' : 'บันทึกและตัดสต็อก'}</button>
          </div>
        )}
      </form>
    </Modal>
  );
}

export default StockDocumentForm;
