import { useCallback, useEffect, useRef, useState } from 'react';
import { AlertTriangle, Pencil, Plus, Search, Trash2, Truck } from 'lucide-react';
import Modal from '../components/Modal';
import Toast from '../components/Toast';
import { api, getRole } from '../lib/api';

const PAGE_LIMIT = 50;

const emptyForm = {
  name: '',
  contact: '',
  area: '',
  note: '',
  is_active: true,
};

function Suppliers() {
  const [suppliers, setSuppliers] = useState([]);
  const [total, setTotal] = useState(0);
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [includeInactive, setIncludeInactive] = useState(false);
  const [offset, setOffset] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingSupplier, setEditingSupplier] = useState(null);
  const [formData, setFormData] = useState(emptyForm);
  const [toast, setToast] = useState('');
  const toastTimerRef = useRef(null);

  const role = getRole();
  const isOwner = role === 'owner';

  const showToast = useCallback((message) => {
    setToast(message);
    if (toastTimerRef.current) {
      window.clearTimeout(toastTimerRef.current);
    }
    toastTimerRef.current = window.setTimeout(() => setToast(''), 2500);
  }, []);

  useEffect(() => {
    return () => {
      if (toastTimerRef.current) {
        window.clearTimeout(toastTimerRef.current);
      }
    };
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setOffset(0);
      setDebouncedSearch(search.trim());
    }, 250);
    return () => window.clearTimeout(timer);
  }, [search]);

  const loadSuppliers = useCallback(async () => {
    setIsLoading(true);
    setErrorMessage('');
    try {
      const params = new URLSearchParams({
        include_inactive: String(includeInactive),
        limit: String(PAGE_LIMIT),
        offset: String(offset),
      });
      if (debouncedSearch) {
        params.set('q', debouncedSearch);
      }
      const data = await api(`/suppliers?${params.toString()}`);
      setSuppliers(Array.isArray(data?.items) ? data.items : []);
      setTotal(typeof data?.total === 'number' ? data.total : 0);
    } catch (error) {
      const message = error.message || 'ไม่สามารถโหลดข้อมูลซัพพลายเออร์ได้';
      setErrorMessage(message);
      showToast(message);
    } finally {
      setIsLoading(false);
    }
  }, [debouncedSearch, includeInactive, offset, showToast]);

  useEffect(() => {
    loadSuppliers();
  }, [loadSuppliers]);

  const handleToggleInactive = (event) => {
    setOffset(0);
    setIncludeInactive(event.target.checked);
  };

  const openCreateModal = () => {
    setEditingSupplier(null);
    setFormData(emptyForm);
    setIsModalOpen(true);
  };

  const openEditModal = (supplier) => {
    if (supplier.is_masked) {
      showToast('ไม่มีสิทธิ์แก้ไขข้อมูลที่ถูกเข้ารหัส');
      return;
    }
    setEditingSupplier(supplier);
    setFormData({
      name: supplier.name || '',
      contact: supplier.contact || '',
      area: supplier.area || '',
      note: supplier.note || '',
      is_active: Boolean(supplier.is_active),
    });
    setIsModalOpen(true);
  };

  const closeModal = () => {
    if (isSaving) return;
    setIsModalOpen(false);
    setEditingSupplier(null);
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    const trimmedName = formData.name.trim();
    if (!trimmedName) {
      showToast('กรุณาระบุชื่อซัพพลายเออร์');
      return;
    }

    const payload = {
      name: trimmedName,
      contact: formData.contact.trim() || null,
      area: formData.area.trim() || null,
      note: formData.note.trim() || null,
      is_active: formData.is_active,
    };

    setIsSaving(true);
    try {
      if (editingSupplier) {
        await api(`/suppliers/${editingSupplier.id}`, {
          method: 'PATCH',
          body: JSON.stringify(payload),
        });
        showToast('แก้ไขข้อมูลซัพพลายเออร์แล้ว');
      } else {
        await api('/suppliers', {
          method: 'POST',
          body: JSON.stringify(payload),
        });
        showToast('เพิ่มซัพพลายเออร์แล้ว');
      }
      setIsModalOpen(false);
      setEditingSupplier(null);
      await loadSuppliers();
    } catch (error) {
      showToast(error.message || 'ไม่สามารถบันทึกข้อมูลซัพพลายเออร์ได้');
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async (supplier) => {
    const displayName = supplier.is_masked ? `#${supplier.id}` : supplier.name;
    if (!window.confirm(`ต้องการลบซัพพลายเออร์ "${displayName}" ใช่หรือไม่?`)) return;

    try {
      await api(`/suppliers/${supplier.id}`, { method: 'DELETE' });
      showToast('ลบซัพพลายเออร์แล้ว');
      if (suppliers.length === 1 && offset > 0) {
        setOffset((prev) => Math.max(0, prev - PAGE_LIMIT));
      } else {
        await loadSuppliers();
      }
    } catch (error) {
      showToast(error.message || 'ไม่สามารถลบซัพพลายเออร์ได้');
    }
  };

  const renderEncryptedField = (value, isMasked, fallback = '-') => {
    if (!value) {
      return <span className="text-slate-400">{fallback}</span>;
    }
    if (isMasked) {
      return (
        <span className="font-mono text-slate-400 break-all" title={value}>
          {value}
        </span>
      );
    }
    return value;
  };

  const pageStart = total === 0 ? 0 : offset + 1;
  const pageEnd = Math.min(offset + suppliers.length, total);
  const hasPrev = offset > 0;
  const hasNext = offset + PAGE_LIMIT < total;

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex items-start gap-3">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-farm-100 text-farm-700">
            <Truck size={22} />
          </div>
          <div>
            <h1 className="text-2xl font-semibold text-slate-800">ซัพพลายเออร์</h1>
            <p className="text-sm text-slate-500">จัดการข้อมูลผู้จำหน่ายวัตถุดิบ</p>
          </div>
        </div>
        <button
          type="button"
          onClick={openCreateModal}
          className="inline-flex items-center justify-center gap-2 rounded-xl bg-farm-700 px-4 py-2.5 text-sm font-semibold text-white shadow-soft transition hover:bg-farm-800"
        >
          <Plus size={16} />
          เพิ่มซัพพลายเออร์
        </button>
      </div>

      {role && !isOwner && (
        <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-xs text-slate-600">
          ข้อมูลซัพพลายเออร์ถูกเข้ารหัสสำหรับสิทธิ์การใช้งานปัจจุบัน ({role})
        </div>
      )}

      <div className="flex flex-col gap-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-soft md:flex-row md:items-center md:justify-between">
        <div className="flex flex-1 items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 focus-within:border-farm-700">
          <Search size={16} className="shrink-0 text-slate-400" />
          <input
            type="text"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            className="w-full bg-transparent text-sm text-slate-700 outline-none placeholder:text-slate-400"
            placeholder="ค้นหาชื่อซัพพลายเออร์"
            aria-label="ค้นหาชื่อซัพพลายเออร์"
          />
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3 md:justify-end">
          <label className="inline-flex cursor-pointer select-none items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700 transition hover:bg-slate-100">
            <input
              type="checkbox"
              checked={includeInactive}
              onChange={handleToggleInactive}
              className="h-4 w-4 rounded border-slate-300 accent-farm-700"
            />
            <span>แสดงรายการที่ปิดใช้งาน</span>
          </label>
          <span className="rounded-full bg-farm-50 px-3 py-1 text-xs font-semibold text-farm-700">
            ทั้งหมด {total} รายการ
          </span>
        </div>
      </div>

      {errorMessage && (
        <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
          {errorMessage}
        </div>
      )}

      <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-soft">
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead className="bg-slate-50 text-slate-600">
              <tr>
                <th className="px-4 py-3 font-semibold">ชื่อ</th>
                <th className="px-4 py-3 font-semibold">ติดต่อ</th>
                <th className="px-4 py-3 font-semibold">พื้นที่</th>
                <th className="px-4 py-3 font-semibold">หมายเหตุ</th>
                <th className="px-4 py-3 font-semibold">สถานะ</th>
                <th className="px-4 py-3 text-right font-semibold">จัดการ</th>
              </tr>
            </thead>
            <tbody>
              {isLoading && (
                <tr>
                  <td colSpan={6} className="px-4 py-8 text-center text-slate-500">
                    กำลังโหลดข้อมูลซัพพลายเออร์...
                  </td>
                </tr>
              )}

              {!isLoading && suppliers.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-4 py-10 text-center text-slate-500">
                    ไม่พบข้อมูลซัพพลายเออร์
                  </td>
                </tr>
              )}

              {!isLoading && suppliers.map((supplier) => {
                const hasDuplicateName = Array.isArray(supplier.warnings)
                  && supplier.warnings.includes('duplicate_name');

                return (
                  <tr key={supplier.id} className="border-t border-slate-100 hover:bg-slate-50">
                    <td className="px-4 py-3 font-medium text-slate-800">
                      <div className="flex flex-wrap items-center gap-2">
                        <span>{renderEncryptedField(supplier.name, supplier.is_masked)}</span>
                        {hasDuplicateName && (
                          <span className="inline-flex items-center gap-1 rounded-full border border-amber-200 bg-amber-50 px-2.5 py-0.5 text-xs font-medium text-amber-700">
                            <AlertTriangle size={12} />
                            ชื่อซ้ำ
                          </span>
                        )}
                        {supplier.decrypt_failed && (
                          <span className="inline-flex items-center gap-1 rounded-full border border-rose-200 bg-rose-50 px-2.5 py-0.5 text-xs font-medium text-rose-700">
                            <AlertTriangle size={12} />
                            ถอดรหัสไม่สำเร็จ
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-slate-600">
                      {renderEncryptedField(supplier.contact, supplier.is_masked)}
                    </td>
                    <td className="px-4 py-3 text-slate-600">
                      {renderEncryptedField(supplier.area, supplier.is_masked)}
                    </td>
                    <td className="max-w-xs px-4 py-3 text-slate-600">
                      {renderEncryptedField(supplier.note, supplier.is_masked)}
                    </td>
                    <td className="px-4 py-3">
                      {supplier.is_active ? (
                        <span className="inline-flex rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-0.5 text-xs font-semibold text-emerald-700">
                          ใช้งาน
                        </span>
                      ) : (
                        <span className="inline-flex rounded-full border border-slate-200 bg-slate-100 px-2.5 py-0.5 text-xs font-semibold text-slate-600">
                          ปิดใช้งาน
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex justify-end gap-2">
                        <button
                          type="button"
                          onClick={() => openEditModal(supplier)}
                          disabled={supplier.is_masked}
                          title={supplier.is_masked ? 'ไม่มีสิทธิ์แก้ไขข้อมูลที่ถูกเข้ารหัส' : 'แก้ไขซัพพลายเออร์'}
                          aria-label="แก้ไขซัพพลายเออร์"
                          className="rounded-lg border border-slate-200 p-2 text-slate-600 transition hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-40"
                        >
                          <Pencil size={15} />
                        </button>
                        <button
                          type="button"
                          onClick={() => handleDelete(supplier)}
                          title="ลบซัพพลายเออร์"
                          aria-label="ลบซัพพลายเออร์"
                          className="rounded-lg border border-slate-200 p-2 text-rose-600 transition hover:bg-rose-50"
                        >
                          <Trash2 size={15} />
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {total > PAGE_LIMIT && (
          <div className="flex flex-col items-center justify-between gap-3 border-t border-slate-100 bg-slate-50/70 px-4 py-3 text-xs text-slate-600 sm:flex-row">
            <span>
              แสดง {pageStart}–{pageEnd} จาก {total} รายการ
            </span>
            <div className="flex items-center gap-2">
              <button
                type="button"
                disabled={!hasPrev || isLoading}
                onClick={() => setOffset((prev) => Math.max(0, prev - PAGE_LIMIT))}
                className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 font-medium text-slate-700 transition hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-50"
              >
                ก่อนหน้า
              </button>
              <button
                type="button"
                disabled={!hasNext || isLoading}
                onClick={() => setOffset((prev) => prev + PAGE_LIMIT)}
                className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 font-medium text-slate-700 transition hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-50"
              >
                ถัดไป
              </button>
            </div>
          </div>
        )}
      </div>

      <Modal
        isOpen={isModalOpen}
        title={editingSupplier ? 'แก้ไขซัพพลายเออร์' : 'เพิ่มซัพพลายเออร์'}
        onClose={closeModal}
      >
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="supplier-name" className="mb-1 block text-sm font-medium text-slate-700">
              ชื่อซัพพลายเออร์ <span className="text-rose-500">*</span>
            </label>
            <input
              id="supplier-name"
              type="text"
              required
              maxLength={160}
              value={formData.name}
              onChange={(event) => setFormData((prev) => ({ ...prev, name: event.target.value }))}
              placeholder="เช่น ร้านเกษตรอินทรีย์รุ่งเรือง"
              className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm text-slate-800 outline-none focus:border-farm-700"
            />
          </div>

          <div>
            <label htmlFor="supplier-contact" className="mb-1 block text-sm font-medium text-slate-700">
              ติดต่อ
            </label>
            <input
              id="supplier-contact"
              type="text"
              maxLength={240}
              value={formData.contact}
              onChange={(event) => setFormData((prev) => ({ ...prev, contact: event.target.value }))}
              placeholder="เบอร์โทร / Line / อีเมล"
              className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm text-slate-800 outline-none focus:border-farm-700"
            />
          </div>

          <div>
            <label htmlFor="supplier-area" className="mb-1 block text-sm font-medium text-slate-700">
              พื้นที่
            </label>
            <input
              id="supplier-area"
              type="text"
              maxLength={500}
              value={formData.area}
              onChange={(event) => setFormData((prev) => ({ ...prev, area: event.target.value }))}
              placeholder="เช่น อำเภอเมือง จังหวัดเชียงใหม่"
              className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm text-slate-800 outline-none focus:border-farm-700"
            />
          </div>

          <div>
            <label htmlFor="supplier-note" className="mb-1 block text-sm font-medium text-slate-700">
              หมายเหตุ
            </label>
            <textarea
              id="supplier-note"
              rows={3}
              maxLength={500}
              value={formData.note}
              onChange={(event) => setFormData((prev) => ({ ...prev, note: event.target.value }))}
              placeholder="รายละเอียดเพิ่มเติม เช่น เงื่อนไขการจัดส่ง"
              className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm text-slate-800 outline-none focus:border-farm-700"
            />
          </div>

          <label className="inline-flex cursor-pointer select-none items-center gap-2 text-sm text-slate-700">
            <input
              type="checkbox"
              checked={formData.is_active}
              onChange={(event) => setFormData((prev) => ({ ...prev, is_active: event.target.checked }))}
              className="h-4 w-4 rounded border-slate-300 accent-farm-700"
            />
            <span>เปิดใช้งานซัพพลายเออร์นี้</span>
          </label>

          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={closeModal}
              disabled={isSaving}
              className="rounded-xl border border-slate-200 px-4 py-2 text-sm font-medium text-slate-600 transition hover:bg-slate-50 disabled:opacity-50"
            >
              ยกเลิก
            </button>
            <button
              type="submit"
              disabled={isSaving}
              className="rounded-xl bg-farm-700 px-4 py-2 text-sm font-semibold text-white transition hover:bg-farm-800 disabled:opacity-60"
            >
              {isSaving ? 'กำลังบันทึก...' : 'บันทึก'}
            </button>
          </div>
        </form>
      </Modal>

      <Toast message={toast} visible={Boolean(toast)} />
    </div>
  );
}

export default Suppliers;
