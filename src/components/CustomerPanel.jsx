import { useEffect, useState } from 'react';
import { Copy, Plus, Trash2, Users } from 'lucide-react';
import { api, getRole } from '../lib/api';

function CustomerPanel() {
  const [customers, setCustomers] = useState([]);
  const [name, setName] = useState('');
  const [contact, setContact] = useState('');
  const [search, setSearch] = useState('');
  const [message, setMessage] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);

  const role = getRole();
  const loadCustomers = async () => {
    try {
      setMessage('');
      const query = role === 'owner' && search.trim() ? `?q=${encodeURIComponent(search.trim())}` : '';
      setCustomers(await api(`/customers${query}`));
    } catch (error) {
      setMessage(error.message);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadCustomers();
  }, [search]);

  const copyCiphertext = async (value) => {
    try {
      await navigator.clipboard.writeText(value);
      setMessage('คัดลอก ciphertext แล้ว');
    } catch {
      setMessage('คัดลอกไม่สำเร็จ กรุณาตรวจสิทธิ์ clipboard ของเบราว์เซอร์');
    }
  };

  const presentValue = (value, customer) => {
    if (!value) return '-';
    if (!customer.is_masked) return value;
    const shortened = value.length > 24 ? `${value.slice(0, 24)}…` : value;
    return (
      <span className="inline-flex max-w-full items-center gap-1.5 align-middle">
        <span className="max-w-[16rem] truncate font-mono text-xs text-slate-400" title={value}>{shortened}</span>
        <button type="button" onClick={() => copyCiphertext(value)} className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700" title="คัดลอก ciphertext เต็ม" aria-label="คัดลอก ciphertext เต็ม">
          <Copy size={13} />
        </button>
      </span>
    );
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (!name.trim()) return;

    setIsSaving(true);
    setMessage('');
    try {
      const customer = await api('/customers', {
        method: 'POST',
        body: JSON.stringify({ name: name.trim(), contact: contact.trim() }),
      });
      setCustomers((current) => [...current, customer]);
      setName('');
      setContact('');
      setMessage('เพิ่มข้อมูลลูกค้าแล้ว');
    } catch (error) {
      setMessage(error.message);
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async (customer) => {
    if (!window.confirm(`ลบข้อมูลลูกค้า ${customer.name} ใช่หรือไม่`)) return;
    try {
      await api(`/customers/${customer.id}`, { method: 'DELETE' });
      setCustomers((current) => current.filter((item) => item.id !== customer.id));
      setMessage('ลบข้อมูลลูกค้าแล้ว');
    } catch (error) {
      setMessage(error.message);
    }
  };

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-soft">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <Users size={19} className="text-farm-700" />
            <h2 className="text-lg font-semibold text-slate-800">ข้อมูลลูกค้า</h2>
          </div>
          <p className="mt-1 text-sm text-slate-500">รายชื่อลูกค้าจากฐานข้อมูลระบบ ERP</p>
        </div>
        <span className="rounded-full bg-farm-50 px-3 py-1 text-sm font-semibold text-farm-700">{customers.length} รายการ</span>
      </div>

      <form onSubmit={handleSubmit} className="mb-5 grid gap-3 md:grid-cols-[1fr_1fr_auto]">
        <input value={name} onChange={(event) => setName(event.target.value)} className="rounded-xl border border-slate-200 px-3 py-2 text-sm outline-none focus:border-farm-700" placeholder="ชื่อลูกค้า" required />
        <input value={contact} onChange={(event) => setContact(event.target.value)} className="rounded-xl border border-slate-200 px-3 py-2 text-sm outline-none focus:border-farm-700" placeholder="เบอร์ติดต่อ / ช่องทางติดต่อ" />
        <button disabled={isSaving} className="inline-flex items-center justify-center gap-2 rounded-xl bg-farm-700 px-4 py-2 text-sm font-semibold text-white transition hover:bg-farm-800 disabled:opacity-60">
          <Plus size={16} />
          {isSaving ? 'กำลังบันทึก' : 'เพิ่มลูกค้า'}
        </button>
      </form>

      {role === 'owner' && <input value={search} onChange={(event) => setSearch(event.target.value)} className="mb-4 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm outline-none focus:border-farm-700" placeholder="ค้นหาชื่อลูกค้า" aria-label="ค้นหาชื่อลูกค้า" />}

      {message && <p className="mb-3 text-sm text-slate-500">{message}</p>}
      <div className="overflow-x-auto">
        <table className="min-w-full text-left text-sm">
          <thead className="border-b border-slate-100 text-slate-500">
            <tr><th className="px-3 py-2 font-semibold">ชื่อลูกค้า</th><th className="px-3 py-2 font-semibold">ติดต่อ</th><th className="px-3 py-2 font-semibold"></th></tr>
          </thead>
          <tbody>
            {isLoading && <tr><td colSpan="3" className="px-3 py-5 text-center text-slate-500">กำลังโหลดข้อมูล...</td></tr>}
            {!isLoading && customers.length === 0 && <tr><td colSpan="3" className="px-3 py-5 text-center text-slate-500">ยังไม่มีข้อมูลลูกค้า</td></tr>}
            {customers.map((customer) => <tr key={customer.id} className="border-b border-slate-50 last:border-0"><td className="px-3 py-3 font-medium text-slate-700">{presentValue(customer.name, customer)}</td><td className="px-3 py-3 text-slate-500">{presentValue(customer.contact, customer)}</td><td className="px-3 py-3 text-right"><button onClick={() => handleDelete(customer)} className="rounded-lg p-2 text-rose-500 hover:bg-rose-50" title="ลบลูกค้า" aria-label="ลบลูกค้า"><Trash2 size={15} /></button></td></tr>)}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export default CustomerPanel;