import { useCallback, useEffect, useState } from 'react';
import { CalendarClock, Leaf, Settings2, Trash2 } from 'lucide-react';
import Modal from '../../components/Modal';
import ThaiDateInput from '../../components/ThaiDateInput';
import { api, getRole } from '../../lib/api';
import { fetchAll } from '../../lib/lookups';
import { cycleName } from '../../utils/itemCategories';
import { formatThaiDate, formatThaiDateTime } from '../../utils/dateUtils';

const inputClass = 'w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm';
const statusLabels = {
  fresh: ['สด', 'bg-emerald-50 text-emerald-700'],
  expiring: ['ใกล้หมดอายุ', 'bg-amber-50 text-amber-700'],
  expired: ['หมดอายุ', 'bg-rose-50 text-rose-700'],
  empty: ['หมดล็อต', 'bg-slate-100 text-slate-500'],
};
const reasonLabels = { expired: 'หมดอายุ', spoiled: 'เน่าเสีย', damaged: 'เสียหาย/ช้ำ', pest: 'โรคหรือแมลง', other: 'อื่น ๆ' };

function FreshStock() {
  const isOwner = getRole() === 'owner';
  const [data, setData] = useState(null);
  const [waste, setWaste] = useState([]);
  const [products, setProducts] = useState([]);
  const [cycleNames, setCycleNames] = useState({});
  const [includeEmpty, setIncludeEmpty] = useState(false);
  const [message, setMessage] = useState('');
  const [dialog, setDialog] = useState(null); // { type: 'setting' | 'waste' | 'expiry', lot? }
  const [form, setForm] = useState({});
  const [error, setError] = useState('');
  const [isSaving, setIsSaving] = useState(false);

  const load = useCallback(async () => {
    try {
      const [lots, wasteData, productData] = await Promise.all([
        api(`/freshness/lots?include_empty=${includeEmpty}`),
        api('/freshness/waste?limit=20'),
        fetchAll('/products'),
      ]);
      setData(lots);
      setWaste(wasteData.items);
      setProducts(productData);
    } catch (err) {
      setMessage(err.message);
    }
  }, [includeEmpty]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    api('/crop-cycles')
      .then((cycles) => setCycleNames(Object.fromEntries(cycles.map((cycle) => [cycle.id, cycleName(cycle)]))))
      .catch(() => {});
  }, []);

  const open = (type, initial, lot = null) => {
    setError('');
    setForm(initial);
    setDialog({ type, lot });
  };
  const update = (changes) => setForm((current) => ({ ...current, ...changes }));

  const submit = async (event) => {
    event.preventDefault();
    const { type, lot } = dialog;
    setIsSaving(true);
    setError('');
    try {
      if (type === 'setting') {
        await api(`/freshness/products/${form.product_id}`, {
          method: 'PUT',
          body: JSON.stringify({ shelf_life_days: Number(form.shelf_life_days), warn_days: Number(form.warn_days) }),
        });
        setMessage('บันทึกอายุการเก็บแล้ว');
      } else if (type === 'waste') {
        await api('/freshness/waste', {
          method: 'POST',
          body: JSON.stringify({ product_id: lot.product_id, lot_key: lot.lot_key, quantity: form.quantity, reason: form.reason, note: form.note || null }),
        });
        setMessage('บันทึกของเสียและตัดสต็อกแล้ว');
      } else {
        await api(`/freshness/products/${lot.product_id}/lots/${lot.lot_key}/expiry`, {
          method: 'PUT', body: JSON.stringify({ expires_on: form.expires_on, reason: form.reason }),
        });
        setMessage('แก้วันหมดอายุแล้ว');
      }
      setDialog(null);
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setIsSaving(false);
    }
  };

  const voidWaste = async (row) => {
    if (!window.confirm('ยกเลิกรายการของเสียนี้ และคืนจำนวนเข้าสต็อก?')) return;
    try {
      await api(`/freshness/waste/${row.id}/void`, { method: 'POST' });
      setMessage('ยกเลิกรายการของเสียแล้ว');
      await load();
    } catch (err) {
      setMessage(err.message);
    }
  };

  const productLabel = (id, name) => (isOwner ? name : `ผลผลิต (ปิดบัง · ลำดับ ${id})`);
  const lotLabel = (lot) => (lot.cycle_id ? cycleNames[lot.cycle_id] || 'รอบปลูก' : 'รับเข้า');

  const pickProduct = (productId) => {
    const current = data?.products.find((item) => String(item.product_id) === productId);
    update({ product_id: productId, shelf_life_days: current?.shelf_life_days ?? '', warn_days: current?.warn_days ?? 1 });
  };

  const untracked = products.filter((product) => product.category === 'vegetable' && !data?.products.some((item) => item.product_id === product.id));
  const titles = { setting: 'ตั้งอายุการเก็บ', waste: 'บันทึกของเสีย', expiry: 'แก้วันหมดอายุของล็อต' };

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-slate-800">ของสด</h1>
          <p className="mt-1 text-sm text-slate-500">ล็อตตามวันเก็บเกี่ยว เรียงให้ส่งล็อตที่หมดอายุก่อน</p>
        </div>
        <button type="button" onClick={() => open('setting', { product_id: '', shelf_life_days: '', warn_days: 1 })} className="inline-flex items-center justify-center gap-2 rounded-xl bg-farm-700 px-4 py-2.5 text-sm font-semibold text-white"><Settings2 size={16} /> ตั้งอายุการเก็บ</button>
      </div>

      {message && <p role="status" className="rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600">{message}</p>}
      {data && (data.expired > 0 || data.expiring > 0) && (
        <p className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">หมดอายุ {data.expired} ล็อต · ใกล้หมดอายุ {data.expiring} ล็อต</p>
      )}
      {untracked.length > 0 && (
        <p className="rounded-xl border border-sky-200 bg-sky-50 px-4 py-3 text-sm text-sky-800">ผัก {untracked.length} รายการยังไม่ได้ตั้งอายุการเก็บ จึงยังไม่ถูกติดตาม</p>
      )}
      {data?.products.filter((item) => item.uncovered_quantity > 0).map((item) => (
        <p key={item.product_id} className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{productLabel(item.product_id, item.product_name)}: ส่งออกมากกว่าที่รับเข้า {item.uncovered_quantity} {item.unit}</p>
      ))}

      <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-soft">
        <div className="flex items-center justify-between border-b border-slate-100 p-4 text-sm">
          <h2 className="font-semibold text-slate-800">ล็อตผลผลิต</h2>
          <label className="flex items-center gap-2"><input type="checkbox" checked={includeEmpty} onChange={(event) => setIncludeEmpty(event.target.checked)} /> แสดงล็อตที่หมดแล้ว</label>
        </div>
        {!data?.items.length ? <p className="p-10 text-center text-sm text-slate-500"><Leaf className="mx-auto mb-2" />{data ? 'ยังไม่มีล็อต ตั้งอายุการเก็บก่อน' : 'กำลังโหลด…'}</p> : (
          <div className="overflow-x-auto">
            <table className="min-w-full whitespace-nowrap text-left text-sm">
              <thead className="bg-slate-50 text-slate-600"><tr>{['ผลผลิต', 'ล็อต', 'วันเก็บ/รับ', 'หมดอายุ', 'คงเหลือ', 'สถานะ', 'จัดการ'].map((head) => <th key={head} className="px-4 py-2 font-semibold">{head}</th>)}</tr></thead>
              <tbody>
                {data.items.map((lot) => {
                  const [label, color] = statusLabels[lot.status];
                  return (
                    <tr key={`${lot.product_id}-${lot.lot_key}`} className="border-t border-slate-100">
                      <td className="px-4 py-3 font-medium text-slate-800">{productLabel(lot.product_id, lot.product_name)}</td>
                      <td className="px-4 py-3">{lotLabel(lot)}</td>
                      <td className="px-4 py-3">{formatThaiDate(lot.received_on)}</td>
                      <td className="px-4 py-3">{formatThaiDate(lot.expires_on)}{lot.expiry_overridden && ' (แก้ไข)'}</td>
                      <td className="px-4 py-3">{lot.remaining_quantity} / {lot.received_quantity} {lot.unit}{lot.wasted_quantity > 0 && ` · เสีย ${lot.wasted_quantity}`}</td>
                      <td className="px-4 py-3"><span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${color}`}>{label}{lot.status === 'expiring' && ` อีก ${lot.days_left} วัน`}</span></td>
                      <td className="px-4 py-3">
                        {lot.status !== 'empty' && (
                          <div className="flex gap-2">
                            <button type="button" onClick={() => open('waste', { quantity: String(lot.remaining_quantity), reason: lot.status === 'expired' ? 'expired' : 'spoiled', note: '' }, lot)} className="inline-flex items-center gap-1 rounded-lg border border-rose-200 px-2 py-1 text-xs text-rose-600"><Trash2 size={13} /> ของเสีย</button>
                            <button type="button" onClick={() => open('expiry', { expires_on: lot.expires_on, reason: '' }, lot)} className="inline-flex items-center gap-1 rounded-lg border border-slate-200 px-2 py-1 text-xs"><CalendarClock size={13} /> แก้วัน</button>
                          </div>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-soft">
        <h2 className="border-b border-slate-100 p-4 text-sm font-semibold text-slate-800">ของเสียล่าสุด</h2>
        {waste.length === 0 ? <p className="p-6 text-center text-sm text-slate-500">ยังไม่มีรายการ</p> : (
          <ul className="divide-y divide-slate-100 text-sm">
            {waste.map((row) => (
              <li key={row.id} className="flex flex-wrap items-center justify-between gap-2 p-4">
                <span className={row.voided ? 'text-slate-400 line-through' : 'text-slate-700'}>
                  {productLabel(row.product_id, row.product_name)} {row.quantity} {row.unit} · {reasonLabels[row.reason]}
                  {row.note && !row.is_masked && ` · ${row.note}`} · {formatThaiDateTime(row.created_at)}
                </span>
                {!row.voided && <button type="button" onClick={() => voidWaste(row)} className="text-xs text-rose-600">ยกเลิกรายการ</button>}
              </li>
            ))}
          </ul>
        )}
      </section>

      <Modal isOpen={Boolean(dialog)} title={dialog ? titles[dialog.type] : ''} onClose={() => !isSaving && setDialog(null)}>
        <form onSubmit={submit} className="space-y-4 text-sm">
          {dialog?.type === 'setting' && (
            <>
              <label className="block">ผลผลิต
                <select required value={form.product_id} onChange={(event) => pickProduct(event.target.value)} className={inputClass}>
                  <option value="">เลือกผลผลิต</option>
                  {products.map((product) => <option key={product.id} value={product.id}>{productLabel(product.id, product.name)}</option>)}
                </select>
              </label>
              <label className="block">เก็บได้กี่วันนับจากวันเก็บเกี่ยว
                <input required type="number" min="0" max="3650" value={form.shelf_life_days} onChange={(event) => update({ shelf_life_days: event.target.value })} className={inputClass} />
              </label>
              <label className="block">เตือนล่วงหน้ากี่วัน
                <input required type="number" min="0" max="3650" value={form.warn_days} onChange={(event) => update({ warn_days: event.target.value })} className={inputClass} />
              </label>
            </>
          )}
          {dialog?.type === 'waste' && (
            <>
              <p>{productLabel(dialog.lot.product_id, dialog.lot.product_name)} · {lotLabel(dialog.lot)} · เหลือ {dialog.lot.remaining_quantity} {dialog.lot.unit}</p>
              <label className="block">ปริมาณ ({dialog.lot.unit})
                <input required type="number" min="0.001" step="0.001" max={dialog.lot.remaining_quantity} value={form.quantity} onChange={(event) => update({ quantity: event.target.value })} className={inputClass} />
              </label>
              <label className="block">สาเหตุ
                <select value={form.reason} onChange={(event) => update({ reason: event.target.value })} className={inputClass}>
                  {Object.entries(reasonLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                </select>
              </label>
              <label className="block">หมายเหตุ
                <input maxLength={1000} value={form.note} onChange={(event) => update({ note: event.target.value })} className={inputClass} />
              </label>
            </>
          )}
          {dialog?.type === 'expiry' && (
            <>
              <div>วันหมดอายุใหม่<ThaiDateInput value={form.expires_on} onChange={(value) => update({ expires_on: value })} required label="วันหมดอายุใหม่" /></div>
              <label className="block">เหตุผล
                <input required maxLength={500} value={form.reason} onChange={(event) => update({ reason: event.target.value })} className={inputClass} />
              </label>
            </>
          )}
          {error && <p role="alert" className="rounded-xl bg-rose-50 p-3 text-rose-700">{error}</p>}
          <button disabled={isSaving} className="w-full rounded-xl bg-farm-700 px-4 py-2.5 font-semibold text-white disabled:opacity-50">{isSaving ? 'กำลังบันทึก…' : 'บันทึก'}</button>
        </form>
      </Modal>
    </div>
  );
}

export default FreshStock;
