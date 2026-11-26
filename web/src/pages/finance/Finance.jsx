import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Ban,
  Calendar,
  Pencil,
  Plus,
  TrendingDown,
  TrendingUp,
  Wallet,
} from 'lucide-react';
import Modal from '../../components/Modal';
import Toast from '../../components/Toast';
import { api, getRole } from '../../lib/api';
import { formatThaiDate, getLocalDateString } from '../../utils/dateUtils';

const PAGE_LIMIT = 50;

const CATEGORIES = [
  'sale',
  'purchase',
  'labor',
  'utilities',
  'equipment',
  'transport',
  'other',
];

const CATEGORY_LABELS = {
  sale: 'ขาย',
  purchase: 'ซื้อวัตถุดิบ',
  labor: 'ค่าแรง',
  utilities: 'สาธารณูปโภค',
  equipment: 'อุปกรณ์',
  transport: 'ค่าขนส่ง',
  other: 'อื่นๆ',
};

const DIRECTION_LABELS = {
  income: 'รายรับ',
  expense: 'รายจ่าย',
};

function getDefaultDateRange() {
  const now = new Date();
  const firstOfMonth = new Date(now.getFullYear(), now.getMonth(), 1);
  return {
    from: getLocalDateString(firstOfMonth),
    to: getLocalDateString(now),
  };
}

function createEmptyForm() {
  return {
    entry_date: getLocalDateString(),
    direction: 'expense',
    category: 'other',
    amount: '',
    description: '',
  };
}

function extractSummaryMetric(metric) {
  if (metric && typeof metric === 'object' && 'value' in metric) {
    return { value: metric.value, isMasked: Boolean(metric.is_masked) };
  }
  return { value: metric, isMasked: false };
}

function formatAmount(amount) {
  if (amount === null || amount === undefined || amount === '') return '-';
  if (typeof amount === 'number') {
    return Number.isFinite(amount) ? `${amount.toLocaleString('th-TH')} ฿` : '-';
  }
  if (typeof amount === 'string' && /^-?\d+(\.\d+)?$/.test(amount.trim())) {
    const parsed = Number(amount);
    if (Number.isFinite(parsed)) {
      return `${parsed.toLocaleString('th-TH')} ฿`;
    }
  }
  return amount;
}

function MaskedIndicator({ label = '••••••' }) {
  return (
    <span
      className="inline-flex items-center gap-1 rounded-md bg-slate-100 px-2 py-0.5 font-mono text-xs text-slate-500"
      title="ข้อมูลถูกปกปิดสำหรับสิทธิ์ผู้ใช้งานนี้"
    >
      {label}
    </span>
  );
}

function Finance() {
  const defaultRange = getDefaultDateRange();
  const role = getRole();
  const isOwner = role === 'owner';

  const [fromDate, setFromDate] = useState(defaultRange.from);
  const [toDate, setToDate] = useState(defaultRange.to);
  const [directionFilter, setDirectionFilter] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [offset, setOffset] = useState(0);

  const [entries, setEntries] = useState([]);
  const [total, setTotal] = useState(0);
  const [summary, setSummary] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');

  const [isFormModalOpen, setIsFormModalOpen] = useState(false);
  const [editingEntry, setEditingEntry] = useState(null);
  const [formData, setFormData] = useState(createEmptyForm);
  const [formError, setFormError] = useState('');
  const [isSaving, setIsSaving] = useState(false);

  const [voidingEntry, setVoidingEntry] = useState(null);
  const [voidReason, setVoidReason] = useState('');
  const [isVoiding, setIsVoiding] = useState(false);

  const [toast, setToast] = useState({ message: '', visible: false });
  const toastTimerRef = useRef(null);

  const showToast = useCallback((message) => {
    if (toastTimerRef.current) {
      window.clearTimeout(toastTimerRef.current);
    }
    setToast({ message, visible: true });
    toastTimerRef.current = window.setTimeout(() => {
      setToast({ message: '', visible: false });
    }, 2600);
  }, []);

  useEffect(() => () => {
    if (toastTimerRef.current) {
      window.clearTimeout(toastTimerRef.current);
    }
  }, []);

  const loadFinanceData = useCallback(async () => {
    if (!fromDate || !toDate) return;
    if (fromDate > toDate) {
      setError('วันที่เริ่มต้นต้องไม่มากกว่าวันที่สิ้นสุด');
      setIsLoading(false);
      return;
    }

    setIsLoading(true);
    setError('');
    try {
      const entryParams = new URLSearchParams({
        from: fromDate,
        to: toDate,
        limit: String(PAGE_LIMIT),
        offset: String(offset),
      });
      if (directionFilter) entryParams.set('direction', directionFilter);
      if (categoryFilter) entryParams.set('category', categoryFilter);
      if (statusFilter) entryParams.set('status', statusFilter);

      const summaryParams = new URLSearchParams({
        from: fromDate,
        to: toDate,
        group_by: 'none',
      });

      const [entriesData, summaryData] = await Promise.all([
        api(`/finance/entries?${entryParams.toString()}`),
        api(`/finance/summary?${summaryParams.toString()}`),
      ]);

      setEntries(Array.isArray(entriesData?.items) ? entriesData.items : []);
      setTotal(typeof entriesData?.total === 'number' ? entriesData.total : 0);
      setSummary(summaryData || null);
    } catch (err) {
      setError(err.message || 'ไม่สามารถโหลดข้อมูลการเงินได้');
    } finally {
      setIsLoading(false);
    }
  }, [fromDate, toDate, directionFilter, categoryFilter, statusFilter, offset]);

  useEffect(() => {
    loadFinanceData();
  }, [loadFinanceData]);

  const handleDateChange = (setter) => (event) => {
    setOffset(0);
    setter(event.target.value);
  };

  const handleFilterChange = (setter) => (event) => {
    setOffset(0);
    setter(event.target.value);
  };

  const openCreateModal = () => {
    setEditingEntry(null);
    setFormData(createEmptyForm());
    setFormError('');
    setIsFormModalOpen(true);
  };

  const openEditModal = (entry) => {
    if (entry.is_auto || entry.status === 'void' || entry.is_masked) return;
    setEditingEntry(entry);
    setFormData({
      entry_date: entry.entry_date || getLocalDateString(),
      direction: entry.direction,
      category: entry.category || 'other',
      amount: entry.amount !== null && entry.amount !== undefined ? String(entry.amount) : '',
      description: entry.description || '',
    });
    setFormError('');
    setIsFormModalOpen(true);
  };

  const closeFormModal = () => {
    if (isSaving) return;
    setIsFormModalOpen(false);
    setEditingEntry(null);
    setFormError('');
  };

  const handleFormSubmit = async (event) => {
    event.preventDefault();
    const numericAmount = Number(formData.amount);
    if (!Number.isFinite(numericAmount) || numericAmount <= 0) {
      setFormError('กรุณากรอกจำนวนเงินที่มากกว่า 0');
      return;
    }

    setIsSaving(true);
    setFormError('');
    try {
      if (editingEntry) {
        await api(`/finance/entries/${editingEntry.id}`, {
          method: 'PATCH',
          body: JSON.stringify({
            entry_date: formData.entry_date || undefined,
            category: formData.category,
            amount: numericAmount,
            description: formData.description.trim() || null,
          }),
        });
        showToast('แก้ไขรายการสำเร็จ');
      } else {
        await api('/finance/entries', {
          method: 'POST',
          body: JSON.stringify({
            entry_date: formData.entry_date || undefined,
            direction: formData.direction,
            category: formData.category,
            amount: numericAmount,
            description: formData.description.trim() || null,
          }),
        });
        showToast('เพิ่มรายการสำเร็จ');
      }
      setIsFormModalOpen(false);
      setEditingEntry(null);
      await loadFinanceData();
    } catch (err) {
      setFormError(err.message || 'ไม่สามารถบันทึกรายการได้');
      showToast(err.message || 'ไม่สามารถบันทึกรายการได้');
    } finally {
      setIsSaving(false);
    }
  };

  const openVoidModal = (entry) => {
    if (entry.is_auto || entry.status === 'void') return;
    setVoidingEntry(entry);
    setVoidReason('');
  };

  const closeVoidModal = () => {
    if (isVoiding) return;
    setVoidingEntry(null);
    setVoidReason('');
  };

  const handleVoidSubmit = async (event) => {
    event.preventDefault();
    if (!voidingEntry) return;

    setIsVoiding(true);
    try {
      await api(`/finance/entries/${voidingEntry.id}/void`, {
        method: 'POST',
        body: JSON.stringify({
          reason: voidReason.trim() || null,
        }),
      });
      setVoidingEntry(null);
      setVoidReason('');
      showToast('ยกเลิกรายการแล้ว');
      await loadFinanceData();
    } catch (err) {
      showToast(err.message || 'ไม่สามารถยกเลิกรายการได้');
    } finally {
      setIsVoiding(false);
    }
  };

  const summaryRow = summary?.items?.[0] || null;
  const fallbackMasked = Boolean(
    extractSummaryMetric(summary?.unallocated_expense).isMasked || (role && !isOwner),
  );
  const incomeMetric = summaryRow
    ? extractSummaryMetric(summaryRow.income)
    : { value: 0, isMasked: fallbackMasked };
  const expenseMetric = summaryRow
    ? extractSummaryMetric(summaryRow.expense)
    : { value: 0, isMasked: fallbackMasked };
  const profitMetric = summaryRow
    ? extractSummaryMetric(summaryRow.profit)
    : { value: 0, isMasked: fallbackMasked };

  const currentPage = Math.floor(offset / PAGE_LIMIT) + 1;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_LIMIT));

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-slate-800">การเงิน</h1>
          <p className="mt-1 text-sm text-slate-500">
            จัดการรายรับ รายจ่าย และดูสรุปกำไร/ขาดทุน
          </p>
        </div>
        <button
          type="button"
          onClick={openCreateModal}
          className="inline-flex items-center justify-center gap-2 rounded-xl bg-farm-700 px-4 py-2.5 text-sm font-semibold text-white shadow-soft transition hover:bg-farm-800"
        >
          <Plus size={16} />
          เพิ่มรายการ
        </button>
      </div>

      {/* Filters & Date Range */}
      <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-soft">
        <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-5">
          <label className="flex flex-col gap-1 text-xs font-medium text-slate-600">
            <span className="inline-flex items-center gap-1.5">
              <Calendar size={14} className="text-slate-400" />
              ตั้งแต่วันที่
            </span>
            <input
              type="date"
              value={fromDate}
              onChange={handleDateChange(setFromDate)}
              className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 outline-none focus:border-farm-700"
            />
          </label>

          <label className="flex flex-col gap-1 text-xs font-medium text-slate-600">
            <span className="inline-flex items-center gap-1.5">
              <Calendar size={14} className="text-slate-400" />
              ถึงวันที่
            </span>
            <input
              type="date"
              value={toDate}
              onChange={handleDateChange(setToDate)}
              className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 outline-none focus:border-farm-700"
            />
          </label>

          <label className="flex flex-col gap-1 text-xs font-medium text-slate-600">
            <span>ประเภท</span>
            <select
              value={directionFilter}
              onChange={handleFilterChange(setDirectionFilter)}
              className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 outline-none focus:border-farm-700"
            >
              <option value="">ทั้งหมด</option>
              <option value="income">รายรับ</option>
              <option value="expense">รายจ่าย</option>
            </select>
          </label>

          <label className="flex flex-col gap-1 text-xs font-medium text-slate-600">
            <span>หมวดหมู่</span>
            <select
              value={categoryFilter}
              onChange={handleFilterChange(setCategoryFilter)}
              className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 outline-none focus:border-farm-700"
            >
              <option value="">ทั้งหมด</option>
              {CATEGORIES.map((category) => (
                <option key={category} value={category}>
                  {CATEGORY_LABELS[category]}
                </option>
              ))}
            </select>
          </label>

          <label className="flex flex-col gap-1 text-xs font-medium text-slate-600">
            <span>สถานะ</span>
            <select
              value={statusFilter}
              onChange={handleFilterChange(setStatusFilter)}
              className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 outline-none focus:border-farm-700"
            >
              <option value="">ทั้งหมด</option>
              <option value="posted">ปกติ</option>
              <option value="void">ยกเลิก</option>
            </select>
          </label>
        </div>
      </section>

      {error && (
        <div
          role="alert"
          className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700"
        >
          {error}
        </div>
      )}

      {/* Summary Cards */}
      <section className="grid gap-4 md:grid-cols-3">
        <div className="rounded-2xl border border-green-200 bg-white p-5 shadow-soft">
          <div className="flex items-start justify-between">
            <div>
              <p className="text-sm font-medium text-slate-500">รายรับ</p>
              <div className="mt-2 text-2xl font-semibold text-green-700">
                {incomeMetric.isMasked ? (
                  <MaskedIndicator />
                ) : (
                  formatAmount(incomeMetric.value)
                )}
              </div>
            </div>
            <div className="rounded-xl bg-green-50 p-3 text-green-600">
              <TrendingUp size={20} />
            </div>
          </div>
          <p className="mt-3 text-xs text-slate-500">
            รวมจากรายการสถานะปกติในช่วงวันที่ที่เลือก
          </p>
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-soft">
          <div className="flex items-start justify-between">
            <div>
              <p className="text-sm font-medium text-slate-500">รายจ่าย</p>
              <div className="mt-2 text-2xl font-semibold text-rose-600">
                {expenseMetric.isMasked ? (
                  <MaskedIndicator />
                ) : (
                  formatAmount(expenseMetric.value)
                )}
              </div>
            </div>
            <div className="rounded-xl bg-rose-50 p-3 text-rose-600">
              <TrendingDown size={20} />
            </div>
          </div>
          <p className="mt-3 text-xs text-slate-500">
            รวมรายจ่ายทั้งหมดในช่วงวันที่ที่เลือก
          </p>
        </div>

        <div className="rounded-2xl border border-emerald-200 bg-white p-5 shadow-soft">
          <div className="flex items-start justify-between">
            <div>
              <p className="text-sm font-medium text-slate-500">กำไร</p>
              <div className="mt-2 text-2xl font-semibold text-emerald-700">
                {profitMetric.isMasked ? (
                  <MaskedIndicator />
                ) : (
                  formatAmount(profitMetric.value)
                )}
              </div>
            </div>
            <div className="rounded-xl bg-emerald-50 p-3 text-emerald-600">
              <Wallet size={20} />
            </div>
          </div>
          <p className="mt-3 text-xs text-slate-500">
            {summaryRow ? `คำนวณจาก ${summaryRow.entry_count} รายการ` : 'ไม่มีรายการในช่วงเวลานี้'}
          </p>
        </div>
      </section>

      {(summary?.truncated || summary?.skipped_decrypt_failed > 0) && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-2.5 text-xs text-amber-800">
          {summary.truncated && 'สรุปยอดถูกจำกัดจำนวนแถวสูงสุดของระบบ '}
          {summary.skipped_decrypt_failed > 0 &&
            `มี ${summary.skipped_decrypt_failed} รายการที่ไม่สามารถถอดรหัสยอดเงินได้`}
        </div>
      )}

      {/* Entries Table */}
      <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-soft">
        <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
          <h2 className="text-base font-semibold text-slate-800">รายการรายรับ-รายจ่าย</h2>
          <span className="text-xs text-slate-500">ทั้งหมด {total} รายการ</span>
        </div>

        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead className="bg-slate-50 text-slate-600">
              <tr>
                <th className="px-4 py-3 font-semibold">วันที่</th>
                <th className="px-4 py-3 font-semibold">ประเภท</th>
                <th className="px-4 py-3 font-semibold">หมวดหมู่</th>
                <th className="px-4 py-3 text-right font-semibold">จำนวนเงิน</th>
                <th className="px-4 py-3 font-semibold">รายละเอียด</th>
                <th className="px-4 py-3 font-semibold">สถานะ</th>
                <th className="px-4 py-3 text-right font-semibold">จัดการ</th>
              </tr>
            </thead>
            <tbody>
              {isLoading && (
                <tr>
                  <td colSpan="7" className="px-4 py-8 text-center text-slate-500">
                    กำลังโหลดข้อมูลการเงิน...
                  </td>
                </tr>
              )}

              {!isLoading && entries.length === 0 && (
                <tr>
                  <td colSpan="7" className="px-4 py-8 text-center text-slate-500">
                    ไม่พบรายการในช่วงเวลาที่เลือก
                  </td>
                </tr>
              )}

              {!isLoading &&
                entries.map((entry) => {
                  const isVoid = entry.status === 'void';
                  const isIncome = entry.direction === 'income';
                  const canModify = !entry.is_auto && !isVoid && !entry.is_masked;
                  const directionColorClass = isIncome
                    ? 'text-green-600'
                    : 'text-red-600';

                  return (
                    <tr
                      key={entry.id}
                      className={`border-t border-slate-100 ${
                        isVoid ? 'bg-slate-50/70 text-slate-400' : 'hover:bg-slate-50'
                      }`}
                    >
                      <td className={`whitespace-nowrap px-4 py-3 ${isVoid ? 'line-through' : 'text-slate-700'}`}>
                        {formatThaiDate(entry.entry_date)}
                      </td>

                      <td className="whitespace-nowrap px-4 py-3">
                        <span
                          className={`font-medium ${directionColorClass} ${
                            isVoid ? 'line-through opacity-60' : ''
                          }`}
                        >
                          {DIRECTION_LABELS[entry.direction] || entry.direction}
                        </span>
                      </td>

                      <td className={`whitespace-nowrap px-4 py-3 ${isVoid ? 'line-through' : 'text-slate-700'}`}>
                        {CATEGORY_LABELS[entry.category] || entry.category}
                      </td>

                      <td className="whitespace-nowrap px-4 py-3 text-right">
                        {entry.is_masked ? (
                          <MaskedIndicator />
                        ) : (
                          <span
                            className={`font-semibold ${directionColorClass} ${
                              isVoid ? 'line-through opacity-60' : ''
                            }`}
                          >
                            {formatAmount(entry.amount)}
                          </span>
                        )}
                      </td>

                      <td className="max-w-xs px-4 py-3">
                        {entry.is_masked && entry.description ? (
                          <MaskedIndicator label="ปกปิดรายละเอียด" />
                        ) : (
                          <div className={isVoid ? 'line-through text-slate-400' : 'text-slate-700'}>
                            {entry.description || '-'}
                          </div>
                        )}
                        {isVoid && entry.void_reason && (
                          <div className="mt-1 text-xs text-rose-500">
                            เหตุผลยกเลิก:{' '}
                            {entry.is_masked ? 'ข้อมูลถูกปกปิด' : entry.void_reason}
                          </div>
                        )}
                      </td>

                      <td className="whitespace-nowrap px-4 py-3">
                        <div className="flex flex-wrap items-center gap-1.5">
                          <span
                            className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${
                              isVoid
                                ? 'bg-rose-100 text-rose-700'
                                : 'bg-emerald-100 text-emerald-700'
                            }`}
                          >
                            {isVoid ? 'ยกเลิก' : 'ปกติ'}
                          </span>
                          {entry.is_auto && (
                            <span className="inline-flex rounded-full bg-sky-100 px-2.5 py-0.5 text-xs font-medium text-sky-700">
                              อัตโนมัติ
                            </span>
                          )}
                          {entry.decrypt_failed && (
                            <span className="inline-flex rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-medium text-amber-800">
                              ถอดรหัสไม่สำเร็จ
                            </span>
                          )}
                        </div>
                      </td>

                      <td className="whitespace-nowrap px-4 py-3 text-right">
                        {canModify ? (
                          <div className="inline-flex items-center gap-1.5">
                            <button
                              type="button"
                              onClick={() => openEditModal(entry)}
                              className="rounded-lg border border-slate-200 p-2 text-slate-600 transition hover:bg-slate-100"
                              title="แก้ไขรายการ"
                              aria-label="แก้ไขรายการ"
                            >
                              <Pencil size={15} />
                            </button>
                            <button
                              type="button"
                              onClick={() => openVoidModal(entry)}
                              className="rounded-lg border border-slate-200 p-2 text-rose-600 transition hover:bg-rose-50"
                              title="ยกเลิกรายการ"
                              aria-label="ยกเลิกรายการ"
                            >
                              <Ban size={15} />
                            </button>
                          </div>
                        ) : (
                          <span className="text-xs text-slate-400">
                            {entry.is_auto ? 'แก้ไขไม่ได้' : '-'}
                          </span>
                        )}
                      </td>
                    </tr>
                  );
                })}
            </tbody>
          </table>
        </div>

        {total > PAGE_LIMIT && (
          <div className="flex items-center justify-between border-t border-slate-100 px-4 py-3 text-sm text-slate-600">
            <span>
              หน้า {currentPage} จาก {totalPages}
            </span>
            <div className="flex items-center gap-2">
              <button
                type="button"
                disabled={offset === 0}
                onClick={() => setOffset((current) => Math.max(0, current - PAGE_LIMIT))}
                className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
              >
                ก่อนหน้า
              </button>
              <button
                type="button"
                disabled={offset + PAGE_LIMIT >= total}
                onClick={() => setOffset((current) => current + PAGE_LIMIT)}
                className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
              >
                ถัดไป
              </button>
            </div>
          </div>
        )}
      </section>

      {/* Create / Edit Modal */}
      <Modal
        isOpen={isFormModalOpen}
        title={editingEntry ? 'แก้ไขรายการการเงิน' : 'เพิ่มรายการ'}
        onClose={closeFormModal}
      >
        <form onSubmit={handleFormSubmit} className="space-y-4">
          {formError && (
            <p className="rounded-xl bg-rose-50 px-3 py-2 text-sm text-rose-600">
              {formError}
            </p>
          )}

          <div className="grid gap-3 sm:grid-cols-2">
            <label className="flex flex-col gap-1 text-sm font-medium text-slate-700">
              <span>ประเภท</span>
              <select
                value={formData.direction}
                disabled={Boolean(editingEntry)}
                onChange={(event) =>
                  setFormData((current) => ({ ...current, direction: event.target.value }))
                }
                className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm outline-none focus:border-farm-700 disabled:bg-slate-100 disabled:text-slate-500"
              >
                <option value="income">รายรับ</option>
                <option value="expense">รายจ่าย</option>
              </select>
            </label>

            <label className="flex flex-col gap-1 text-sm font-medium text-slate-700">
              <span>หมวดหมู่</span>
              <select
                value={formData.category}
                onChange={(event) =>
                  setFormData((current) => ({ ...current, category: event.target.value }))
                }
                className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm outline-none focus:border-farm-700"
              >
                {CATEGORIES.map((category) => (
                  <option key={category} value={category}>
                    {CATEGORY_LABELS[category]}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <label className="flex flex-col gap-1 text-sm font-medium text-slate-700">
              <span>จำนวนเงิน (บาท)</span>
              <input
                type="number"
                min="0.01"
                step="0.01"
                required
                value={formData.amount}
                onChange={(event) =>
                  setFormData((current) => ({ ...current, amount: event.target.value }))
                }
                placeholder="0.00"
                className="rounded-xl border border-slate-200 px-3 py-2 text-sm outline-none focus:border-farm-700"
              />
            </label>

            <label className="flex flex-col gap-1 text-sm font-medium text-slate-700">
              <span className="inline-flex items-center gap-1.5">
                <Calendar size={14} className="text-slate-400" />
                วันที่รายการ
              </span>
              <input
                type="date"
                required
                value={formData.entry_date}
                onChange={(event) =>
                  setFormData((current) => ({ ...current, entry_date: event.target.value }))
                }
                className="rounded-xl border border-slate-200 px-3 py-2 text-sm outline-none focus:border-farm-700"
              />
            </label>
          </div>

          <label className="flex flex-col gap-1 text-sm font-medium text-slate-700">
            <span>รายละเอียด</span>
            <textarea
              rows={3}
              maxLength={500}
              value={formData.description}
              onChange={(event) =>
                setFormData((current) => ({ ...current, description: event.target.value }))
              }
              placeholder="ระบุรายละเอียดเพิ่มเติม (ถ้ามี)"
              className="rounded-xl border border-slate-200 px-3 py-2 text-sm outline-none focus:border-farm-700"
            />
          </label>

          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={closeFormModal}
              disabled={isSaving}
              className="rounded-xl border border-slate-200 px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50"
            >
              ยกเลิก
            </button>
            <button
              type="submit"
              disabled={isSaving}
              className="rounded-xl bg-farm-700 px-4 py-2 text-sm font-semibold text-white hover:bg-farm-800 disabled:opacity-60"
            >
              {isSaving ? 'กำลังบันทึก...' : 'บันทึก'}
            </button>
          </div>
        </form>
      </Modal>

      {/* Void Reason Modal */}
      <Modal
        isOpen={Boolean(voidingEntry)}
        title="ยืนยันการยกเลิกรายการ"
        onClose={closeVoidModal}
      >
        <form onSubmit={handleVoidSubmit} className="space-y-4">
          {voidingEntry && (
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-3 text-sm text-slate-600">
              <p>
                วันที่: <span className="font-medium text-slate-800">{formatThaiDate(voidingEntry.entry_date)}</span>
              </p>
              <p className="mt-1">
                รายการ:{' '}
                <span className="font-medium text-slate-800">
                  {DIRECTION_LABELS[voidingEntry.direction]} ·{' '}
                  {CATEGORY_LABELS[voidingEntry.category] || voidingEntry.category}
                </span>
              </p>
              <p className="mt-1">
                จำนวนเงิน:{' '}
                <span className="font-semibold text-slate-800">
                  {voidingEntry.is_masked ? '••••••' : formatAmount(voidingEntry.amount)}
                </span>
              </p>
            </div>
          )}

          <label className="flex flex-col gap-1 text-sm font-medium text-slate-700">
            <span>เหตุผลการยกเลิก</span>
            <input
              type="text"
              maxLength={500}
              value={voidReason}
              onChange={(event) => setVoidReason(event.target.value)}
              placeholder="ระบุเหตุผลการยกเลิก (ถ้ามี)"
              className="rounded-xl border border-slate-200 px-3 py-2 text-sm outline-none focus:border-farm-700"
            />
          </label>

          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={closeVoidModal}
              disabled={isVoiding}
              className="rounded-xl border border-slate-200 px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50"
            >
              ปิด
            </button>
            <button
              type="submit"
              disabled={isVoiding}
              className="inline-flex items-center gap-1.5 rounded-xl bg-rose-600 px-4 py-2 text-sm font-semibold text-white hover:bg-rose-700 disabled:opacity-60"
            >
              <Ban size={15} />
              {isVoiding ? 'กำลังยกเลิก...' : 'ยืนยันยกเลิกรายการ'}
            </button>
          </div>
        </form>
      </Modal>

      <Toast message={toast.message} visible={toast.visible} />
    </div>
  );
}

export default Finance;
