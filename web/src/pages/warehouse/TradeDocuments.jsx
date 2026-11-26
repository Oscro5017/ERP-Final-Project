import { Fragment, useEffect, useRef, useState } from 'react';
import {
  ArrowDownToLine,
  ArrowUpFromLine,
  Ban,
  ChevronDown,
  ChevronUp,
  Eye,
  FileText,
  Plus,
} from 'lucide-react';
import Modal from '../../components/Modal';
import StockDocumentForm from '../../components/StockDocumentForm';
import ThaiDateInput from '../../components/ThaiDateInput';
import Toast from '../../components/Toast';
import { formatStockWarning } from '../../utils/stockWarnings';
import { api, getRole } from '../../lib/api';
import { formatThaiDate, formatThaiDateTime } from '../../utils/dateUtils';

const PAGE_LIMIT = 50;

function formatNumber(value, decimals = 2) {
  if (value === null || value === undefined || value === '') return '-';
  const num = Number(value);
  if (Number.isNaN(num)) return String(value);
  return num.toLocaleString('th-TH', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

function formatQuantity(value) {
  if (value === null || value === undefined || value === '') return '-';
  const num = Number(value);
  if (Number.isNaN(num)) return String(value);
  return num.toLocaleString('th-TH', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 3,
  });
}

function getTotalAmountMeta(doc) {
  if (doc.total_amount === null || doc.total_amount === undefined) {
    return { value: null, isMasked: Boolean(doc.is_masked) };
  }
  if (typeof doc.total_amount === 'object') {
    return {
      value: doc.total_amount.value ?? null,
      isMasked: Boolean(doc.total_amount.is_masked ?? doc.is_masked),
    };
  }
  return { value: doc.total_amount, isMasked: Boolean(doc.is_masked) };
}

function MaskedText({ value, isMasked, fallback = '-', className = '', strikethrough = false }) {
  if (value === null || value === undefined || value === '') {
    return <span className={className}>{fallback}</span>;
  }
  const text = String(value);
  if (!isMasked) {
    return (
      <span className={`${strikethrough ? 'line-through' : ''} ${className}`}>
        {text}
      </span>
    );
  }
  const shortened = text.length > 20 ? `${text.slice(0, 20)}…` : text;
  return (
    <span
      title={text}
      className={`inline-flex max-w-[14rem] items-center truncate rounded-md bg-slate-100 px-2 py-0.5 font-mono text-xs text-slate-400 select-none ${strikethrough ? 'line-through' : ''} ${className}`}
    >
      {shortened}
    </span>
  );
}

const PURPOSE_LABELS = { sale: 'ส่งขาย', order: 'ส่งตามออเดอร์', other: 'ส่งออกอื่น ๆ' };

/** Stock documents; salesOnly shows just the outbound ones that are sales. */
function TradeDocuments({ salesOnly = false }) {
  const role = getRole();
  const isOwner = role === 'owner';

  const [documents, setDocuments] = useState([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');

  const [docTypeTab, setDocTypeTab] = useState('');
  const [fromDate, setFromDate] = useState('');
  const [toDate, setToDate] = useState('');
  const [statusFilter, setStatusFilter] = useState('');

  const [expandedIds, setExpandedIds] = useState({});

  const [createDocType, setCreateDocType] = useState(null);

  const [editTarget, setEditTarget] = useState(null);
  const [editForm, setEditForm] = useState({ reference_no: '', note: '' });
  const [isUpdating, setIsUpdating] = useState(false);

  const [voidTarget, setVoidTarget] = useState(null);
  const [voidReason, setVoidReason] = useState('');
  const [isVoiding, setIsVoiding] = useState(false);

  const [toast, setToast] = useState('');
  const toastTimerRef = useRef(null);

  const showToast = (message) => {
    setToast(message);
    if (toastTimerRef.current) window.clearTimeout(toastTimerRef.current);
    toastTimerRef.current = window.setTimeout(() => setToast(''), 5000);
  };

  useEffect(() => {
    return () => {
      if (toastTimerRef.current) window.clearTimeout(toastTimerRef.current);
    };
  }, []);

  const loadDocuments = async (nextOffset = offset) => {
    if (fromDate && toDate && fromDate > toDate) {
      setError('วันที่เริ่มต้นต้องไม่มากกว่าวันที่สิ้นสุด');
      setIsLoading(false);
      return;
    }
    setIsLoading(true);
    setError('');
    try {
      const params = new URLSearchParams();
      if (salesOnly) params.set('sales_only', 'true');
      if (docTypeTab) params.set('doc_type', docTypeTab);
      if (fromDate) params.set('from', fromDate);
      if (toDate) params.set('to', toDate);
      if (statusFilter) params.set('status', statusFilter);
      params.set('limit', String(PAGE_LIMIT));
      params.set('offset', String(nextOffset));

      const data = await api(`/trade/documents?${params.toString()}`);
      setDocuments(data?.items || []);
      setTotal(data?.total ?? 0);
    } catch (err) {
      setError(err.message);
      showToast(err.message);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    setOffset(0);
    loadDocuments(0);
  }, [docTypeTab, fromDate, toDate, statusFilter]);

  const handlePageChange = (nextOffset) => {
    setOffset(nextOffset);
    loadDocuments(nextOffset);
  };

  const toggleExpand = (docId) => {
    setExpandedIds((prev) => ({ ...prev, [docId]: !prev[docId] }));
  };

  const recordFinance = async (doc) => {
    try {
      const updated = await api(`/trade/documents/${doc.id}/finance`, { method: 'POST' });
      setDocuments((prev) => prev.map((item) => (item.id === updated.id ? updated : item)));
      showToast(`ลงบัญชีเอกสาร ${updated.doc_no} แล้ว`);
    } catch (err) {
      showToast(err.message);
    }
  };

  const openEditModal = (doc) => {
    setEditTarget(doc);
    setEditForm({
      reference_no: doc.reference_no || '',
      note: doc.is_masked ? '' : doc.note || '',
    });
  };

  const handleEditSubmit = async (event) => {
    event.preventDefault();
    if (!editTarget) return;

    const payload = {
      reference_no: editForm.reference_no.trim() || null,
    };
    if (!editTarget.is_masked || editForm.note.trim()) {
      payload.note = editForm.note.trim() || null;
    }

    setIsUpdating(true);
    try {
      const updated = await api(`/trade/documents/${editTarget.id}`, {
        method: 'PATCH',
        body: JSON.stringify(payload),
      });
      setDocuments((prev) => prev.map((item) => (item.id === updated.id ? updated : item)));
      setEditTarget(null);
      showToast(`อัปเดตเอกสาร ${updated.doc_no} แล้ว`);
    } catch (err) {
      showToast(err.message);
    } finally {
      setIsUpdating(false);
    }
  };

  const openVoidModal = (doc) => {
    setVoidTarget(doc);
    setVoidReason('');
  };

  const handleVoidSubmit = async (event) => {
    event.preventDefault();
    if (!voidTarget) return;
    setIsVoiding(true);
    try {
      const updated = await api(`/trade/documents/${voidTarget.id}/void`, {
        method: 'POST',
        body: JSON.stringify({
          reason: voidReason.trim() || null,
        }),
      });
      setDocuments((prev) => prev.map((item) => (item.id === updated.id ? updated : item)));
      setVoidTarget(null);
      showToast(`ยกเลิกเอกสาร ${updated.doc_no} แล้ว`);
    } catch (err) {
      showToast(err.message);
    } finally {
      setIsVoiding(false);
    }
  };

  const clearFilters = () => {
    setDocTypeTab('');
    setFromDate('');
    setToDate('');
    setStatusFilter('');
  };

  const getPartnerDisplay = (doc) => {
    const isVoid = doc.status === 'void';
    if (doc.doc_type === 'inbound') {
      if (doc.supplier_name) {
        return <MaskedText value={doc.supplier_name} isMasked={doc.is_masked} strikethrough={isVoid} />;
      }
      if (doc.supplier_id) {
        return <span className={isVoid ? 'line-through' : ''}>ซัพพลายเออร์ (ไม่พบชื่อ)</span>;
      }
      return <span className="text-slate-400">-</span>;
    }
    if (doc.customer_name) {
      return <MaskedText value={doc.customer_name} isMasked={doc.is_masked} strikethrough={isVoid} />;
    }
    if (doc.customer_id) {
      return <span className={isVoid ? 'line-through' : ''}>ลูกค้า (ไม่พบชื่อ)</span>;
    }
    return <span className="text-slate-400">-</span>;
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <div className="flex items-center gap-2.5">
            <FileText size={24} className="text-farm-700" />
            <h1 className="text-2xl font-semibold text-slate-800">{salesOnly ? 'รายการขาย' : 'รับเข้า-ส่งออก'}</h1>
          </div>
          <p className="mt-1 text-sm text-slate-500">{salesOnly ? 'การส่งขายและส่งตามออเดอร์ พร้อมยอดและสถานะรายรับ' : 'รับของเข้าคลังและส่งของออก'}</p>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          {!salesOnly && <button
            type="button"
            onClick={() => setCreateDocType('inbound')}
            className="inline-flex items-center gap-2 rounded-xl bg-farm-700 px-4 py-2.5 text-sm font-semibold text-white shadow-soft transition hover:bg-farm-800"
          >
            <Plus size={16} />
            <ArrowDownToLine size={16} />
            รับเข้า
          </button>}
          <button
            type="button"
            onClick={() => setCreateDocType('outbound')}
            className="inline-flex items-center gap-2 rounded-xl border border-farm-700 bg-white px-4 py-2.5 text-sm font-semibold text-farm-700 shadow-soft transition hover:bg-farm-50"
          >
            <Plus size={16} />
            <ArrowUpFromLine size={16} />
            {salesOnly ? 'บันทึกการขาย' : 'ส่งออก'}
          </button>
        </div>
      </div>

      {!isOwner && role && (
        <div className="rounded-xl border border-amber-200 bg-amber-50/70 px-4 py-2.5 text-xs text-amber-800">
          สิทธิ์ผู้ใช้งาน ({role}): ข้อมูลราคา ยอดเงิน ชื่อคู่ค้า และหมายเหตุบางส่วนถูกเข้ารหัสแสดงผล (Masked)
        </div>
      )}

      {/* Tabs + Filters */}
      <div className="space-y-4 rounded-2xl border border-slate-200 bg-white p-4 shadow-soft">
        <div className="flex flex-col gap-3 border-b border-slate-100 pb-3 sm:flex-row sm:items-center sm:justify-between">
          <div className={`${salesOnly ? 'hidden' : 'inline-flex'} rounded-xl bg-slate-100 p-1`} role="tablist" aria-label="ประเภทเอกสาร">
            {[
              { value: '', label: 'ทั้งหมด' },
              { value: 'inbound', label: 'รับเข้า' },
              { value: 'outbound', label: 'ส่งออก' },
            ].map((tab) => (
              <button
                key={tab.value || 'all'}
                type="button"
                role="tab"
                aria-selected={docTypeTab === tab.value}
                onClick={() => setDocTypeTab(tab.value)}
                className={`rounded-lg px-4 py-1.5 text-sm font-medium transition ${
                  docTypeTab === tab.value
                    ? 'bg-white text-farm-800 shadow-sm'
                    : 'text-slate-600 hover:text-slate-800'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          <span className="text-xs text-slate-500">ทั้งหมด {total.toLocaleString('th-TH')} รายการ</span>
        </div>

        <div className="grid gap-3 md:grid-cols-4">
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-600">ตั้งแต่วันที่</label>
            <ThaiDateInput value={fromDate} onChange={setFromDate} label="ตั้งแต่วันที่" />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-600">ถึงวันที่</label>
            <ThaiDateInput value={toDate} onChange={setToDate} label="ถึงวันที่" />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-600">สถานะ</label>
            <select
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value)}
              className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700"
              aria-label="กรองสถานะเอกสาร"
            >
              <option value="">ทุกสถานะ</option>
              <option value="posted">บันทึกแล้ว (Posted)</option>
              <option value="void">ยกเลิกแล้ว (Void)</option>
            </select>
          </div>
          <div className="flex items-end">
            <button
              type="button"
              onClick={clearFilters}
              className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm font-medium text-slate-600 transition hover:bg-slate-50"
            >
              ล้างตัวกรอง
            </button>
          </div>
        </div>
      </div>

      {error && (
        <div role="alert" className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
          {error}
        </div>
      )}

      {/* Documents Table */}
      <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-soft">
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead className="bg-slate-50 text-slate-600">
              <tr>
                <th className="w-10 px-3 py-3" aria-label="ขยายแถว" />
                <th className="px-4 py-3 font-semibold">เลขที่</th>
                <th className="px-4 py-3 font-semibold">ประเภท</th>
                <th className="px-4 py-3 font-semibold">วันที่</th>
                <th className="px-4 py-3 font-semibold">คู่ค้า</th>
                <th className="px-4 py-3 text-right font-semibold">ยอดรวม</th>
                <th className="px-4 py-3 font-semibold">สถานะ</th>
                <th className="px-4 py-3 text-right font-semibold">จัดการ</th>
              </tr>
            </thead>
            <tbody>
              {isLoading && (
                <tr>
                  <td colSpan={8} className="px-4 py-10 text-center text-slate-500">
                    กำลังโหลดข้อมูลเอกสาร...
                  </td>
                </tr>
              )}
              {!isLoading && documents.length === 0 && (
                <tr>
                  <td colSpan={8} className="px-4 py-12 text-center text-slate-500">
                    ไม่พบเอกสารตามเงื่อนไขที่เลือก
                  </td>
                </tr>
              )}
              {!isLoading &&
                documents.map((doc) => {
                  const isExpanded = Boolean(expandedIds[doc.id]);
                  const isVoid = doc.status === 'void';
                  const isInbound = doc.doc_type === 'inbound';
                  const totalMeta = getTotalAmountMeta(doc);

                  return (
                    <Fragment key={doc.id}>
                      <tr
                        onClick={() => toggleExpand(doc.id)}
                        className={`cursor-pointer border-t border-slate-100 transition hover:bg-slate-50/80 ${
                          isVoid ? 'bg-slate-50/60 text-slate-400' : ''
                        }`}
                      >
                        <td className="px-3 py-3 text-slate-400">
                          {isExpanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                        </td>
                        <td className="px-4 py-3 font-medium">
                          <div className={`whitespace-nowrap ${isVoid ? 'text-slate-400 line-through' : 'text-slate-800'}`}>
                            {doc.doc_no}
                          </div>
                          {doc.reference_no && (
                            <div className={`text-xs text-slate-400 ${isVoid ? 'line-through' : ''}`}>
                              อ้างอิง: {doc.reference_no}
                            </div>
                          )}
                        </td>
                        <td className="px-4 py-3">
                          {isInbound ? (
                            <span className="inline-flex items-center gap-1 whitespace-nowrap rounded-full bg-emerald-100 px-2.5 py-1 text-xs font-semibold text-emerald-700">
                              <ArrowDownToLine size={12} />
                              รับเข้า
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1 whitespace-nowrap rounded-full bg-sky-100 px-2.5 py-1 text-xs font-semibold text-sky-700">
                              <ArrowUpFromLine size={12} />
                              {PURPOSE_LABELS[doc.purpose] || 'ส่งออก (ไม่ระบุ)'}
                            </span>
                          )}
                          {doc.order_no && <div className="mt-1 text-xs text-slate-500">{doc.order_no}</div>}
                        </td>
                        <td className={`px-4 py-3 ${isVoid ? 'text-slate-400 line-through' : 'text-slate-700'}`}>
                          {formatThaiDate(doc.doc_date)}
                        </td>
                        <td className={`px-4 py-3 ${isVoid ? 'text-slate-400' : 'text-slate-700'}`}>
                          {getPartnerDisplay(doc)}
                        </td>
                        <td className="whitespace-nowrap px-4 py-3 text-right">
                          {totalMeta.value === null ? '-' : totalMeta.isMasked ? '••••••' : formatNumber(totalMeta.value)}
                          {totalMeta.value !== null && !isVoid && (
                            <div className={`text-xs ${doc.finance_recorded ? 'text-emerald-700' : 'text-amber-700'}`}>
                              {doc.finance_recorded ? 'ลงบัญชีแล้ว' : 'ยังไม่ลงบัญชี'}
                            </div>
                          )}
                        </td>
                        <td className="px-4 py-3">
                          <div className="space-y-1">
                            {isVoid ? (
                              <span className="inline-flex items-center gap-1 whitespace-nowrap rounded-full bg-rose-100 px-2.5 py-1 text-xs font-semibold text-rose-700 line-through">
                                ยกเลิกแล้ว
                              </span>
                            ) : (
                              <span className="inline-flex items-center whitespace-nowrap rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-semibold text-emerald-700">
                                บันทึกแล้ว
                              </span>
                            )}
                            {isVoid && (
                              <div className="text-xs text-rose-600">
                                เหตุผล:{' '}
                                {doc.void_reason ? (
                                  <MaskedText value={doc.void_reason} isMasked={doc.is_masked} />
                                ) : (
                                  '-'
                                )}
                              </div>
                            )}
                          </div>
                        </td>
                        <td className="px-4 py-3 text-right">
                          <div className="inline-flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
                            <button
                              type="button"
                              onClick={() => toggleExpand(doc.id)}
                              className="inline-flex items-center gap-1 whitespace-nowrap rounded-lg px-2.5 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-100"
                              title="ดูรายละเอียด"
                              aria-label={`ดูรายละเอียด ${doc.doc_no}`}
                            >
                              <Eye size={14} />
                              <span className="hidden sm:inline">{isExpanded ? 'ซ่อน' : 'ดูรายการ'}</span>
                            </button>
                            {!isVoid && !doc.finance_recorded && totalMeta.value !== null && (
                              <button type="button" onClick={() => recordFinance(doc)} className="whitespace-nowrap rounded-lg px-2.5 py-1.5 text-xs font-medium text-farm-700 hover:bg-farm-50">
                                {isInbound ? 'ลงรายจ่าย' : 'ลงรายรับ'}
                              </button>
                            )}
                            {!isVoid && (
                              <button
                                type="button"
                                onClick={() => openVoidModal(doc)}
                                className="inline-flex items-center gap-1 whitespace-nowrap rounded-lg px-2.5 py-1.5 text-xs font-medium text-rose-600 hover:bg-rose-50"
                                title="ยกเลิกเอกสาร"
                                aria-label={`ยกเลิกเอกสาร ${doc.doc_no}`}
                              >
                                <Ban size={14} />
                                <span className="hidden sm:inline">ยกเลิก</span>
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>

                      {isExpanded && (
                        <tr className="border-t border-slate-100 bg-slate-50/70">
                          <td colSpan={8} className="px-6 py-4">
                            <div className="space-y-4">
                              {/* Metadata & Actions */}
                              <div className="flex flex-col gap-3 rounded-xl border border-slate-200 bg-white p-4 sm:flex-row sm:items-start sm:justify-between">
                                <div className="grid flex-1 gap-2 text-xs text-slate-600 sm:grid-cols-2 lg:grid-cols-4">
                                  <div>
                                    <span className="text-slate-400">เลขที่อ้างอิง: </span>
                                    <span className={isVoid ? 'line-through' : 'font-medium text-slate-700'}>
                                      {doc.reference_no || '-'}
                                    </span>
                                  </div>
                                  <div>
                                    <span className="text-slate-400">รอบปลูก: </span>
                                    <span className="font-medium text-slate-700">{doc.crop_cycle_label || '-'}</span>
                                  </div>
                                  <div>
                                    <span className="text-slate-400">ยอดรวม: </span>
                                    {totalMeta.value !== null ? (
                                      totalMeta.isMasked ? (
                                        <MaskedText value={totalMeta.value} isMasked strikethrough={isVoid} />
                                      ) : (
                                        <span className={`font-semibold text-slate-800 ${isVoid ? 'line-through' : ''}`}>
                                          {formatNumber(totalMeta.value)} บาท
                                        </span>
                                      )
                                    ) : (
                                      <span>-</span>
                                    )}
                                  </div>
                                  <div>
                                    <span className="text-slate-400">สร้างเมื่อ: </span>
                                    <span>{formatThaiDateTime(doc.created_at)}</span>
                                  </div>
                                  <div className="sm:col-span-2 lg:col-span-4">
                                    <span className="text-slate-400">หมายเหตุ: </span>
                                    {doc.note ? (
                                      <MaskedText value={doc.note} isMasked={doc.is_masked} strikethrough={isVoid} />
                                    ) : (
                                      <span>-</span>
                                    )}
                                  </div>
                                  {isVoid && (
                                    <div className="sm:col-span-2 lg:col-span-4 text-rose-700">
                                      <span className="font-medium">ยกเลิกเมื่อ {formatThaiDateTime(doc.voided_at)}</span>
                                      {' · '}
                                      <span>เหตุผล: </span>
                                      {doc.void_reason ? (
                                        <MaskedText value={doc.void_reason} isMasked={doc.is_masked} />
                                      ) : (
                                        <span>ไม่ได้ระบุ</span>
                                      )}
                                    </div>
                                  )}
                                  {doc.warnings?.length > 0 && (
                                    <div className="sm:col-span-2 lg:col-span-4 rounded-lg bg-amber-50 px-3 py-1.5 text-amber-700">
                                      คำเตือน: {doc.warnings.map((warning) => formatStockWarning(warning, doc.is_masked ? {} : Object.fromEntries(doc.lines.map((line) => [line.product_id, line.product_name])))).join(', ')}
                                    </div>
                                  )}
                                </div>

                                {!isVoid && (
                                  <div className="flex shrink-0 items-center gap-2">
                                    <button
                                      type="button"
                                      onClick={() => openEditModal(doc)}
                                      className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
                                    >
                                      แก้ไขอ้างอิง/หมายเหตุ
                                    </button>
                                  </div>
                                )}
                              </div>

                              {/* Line Items Table */}
                              <div className="overflow-hidden rounded-xl border border-slate-200 bg-white">
                                <table className="min-w-full text-left text-xs">
                                  <thead className="bg-slate-50 text-slate-500">
                                    <tr>
                                      <th className="px-3 py-2 font-semibold">#</th>
                                      <th className="px-3 py-2 font-semibold">รายการ</th>
                                      <th className="px-3 py-2 text-right font-semibold">จำนวน</th>
                                      <th className="px-3 py-2 font-semibold">หน่วย</th>
                                      <th className="px-3 py-2 text-right font-semibold">ราคา/หน่วย</th>
                                      <th className="px-3 py-2 text-right font-semibold">รวมเป็นเงิน</th>
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {(!doc.lines || doc.lines.length === 0) && (
                                      <tr>
                                        <td colSpan={6} className="px-3 py-4 text-center text-slate-400">
                                          ไม่มีรายการ
                                        </td>
                                      </tr>
                                    )}
                                    {(doc.lines || []).map((line) => {
                                      const lineMasked = Boolean(line.is_masked || doc.is_masked);
                                      return (
                                        <tr
                                          key={line.id || line.line_no}
                                          className={`border-t border-slate-100 ${isVoid ? 'text-slate-400 line-through' : 'text-slate-700'}`}
                                        >
                                          <td className="px-3 py-2">{line.line_no}</td>
                                          <td className="px-3 py-2">
                                            <MaskedText
                                              value={line.product_name}
                                              isMasked={lineMasked}
                                              strikethrough={isVoid}
                                            />
                                          </td>
                                          <td className="px-3 py-2 text-right">{formatQuantity(line.quantity)}</td>
                                          <td className="px-3 py-2">{line.unit || '-'}</td>
                                          <td className="px-3 py-2 text-right">
                                            {line.unit_price !== null && line.unit_price !== undefined ? (
                                              lineMasked ? (
                                                <MaskedText value={line.unit_price} isMasked strikethrough={isVoid} />
                                              ) : (
                                                formatNumber(line.unit_price)
                                              )
                                            ) : (
                                              '-'
                                            )}
                                          </td>
                                          <td className="px-3 py-2 text-right font-medium">
                                            {line.line_amount !== null && line.line_amount !== undefined ? (
                                              lineMasked ? (
                                                <MaskedText value={line.line_amount} isMasked strikethrough={isVoid} />
                                              ) : (
                                                formatNumber(line.line_amount)
                                              )
                                            ) : (
                                              '-'
                                            )}
                                          </td>
                                        </tr>
                                      );
                                    })}
                                  </tbody>
                                </table>
                              </div>
                            </div>
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {total > PAGE_LIMIT && (
          <div className="flex items-center justify-between border-t border-slate-100 px-4 py-3 text-xs text-slate-600">
            <span>
              แสดง {offset + 1} - {Math.min(offset + documents.length, total)} จาก {total} รายการ
            </span>
            <div className="flex items-center gap-2">
              <button
                type="button"
                disabled={offset === 0 || isLoading}
                onClick={() => handlePageChange(Math.max(0, offset - PAGE_LIMIT))}
                className="rounded-lg border border-slate-200 px-3 py-1.5 font-medium hover:bg-slate-50 disabled:opacity-40"
              >
                ก่อนหน้า
              </button>
              <button
                type="button"
                disabled={offset + PAGE_LIMIT >= total || isLoading}
                onClick={() => handlePageChange(offset + PAGE_LIMIT)}
                className="rounded-lg border border-slate-200 px-3 py-1.5 font-medium hover:bg-slate-50 disabled:opacity-40"
              >
                ถัดไป
              </button>
            </div>
          </div>
        )}
      </div>

      <StockDocumentForm
        docType={createDocType}
        onClose={() => setCreateDocType(null)}
        onSaved={(text) => { setCreateDocType(null); showToast(text); setOffset(0); loadDocuments(0); }}
      />

      {/* Edit Reference / Note Modal */}
      <Modal
        isOpen={Boolean(editTarget)}
        title={`แก้ไขเอกสาร ${editTarget?.doc_no || ''}`}
        onClose={() => !isUpdating && setEditTarget(null)}
      >
        <form onSubmit={handleEditSubmit} className="space-y-4 text-sm">
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-600">เลขที่อ้างอิง</label>
            <input
              type="text"
              maxLength={120}
              value={editForm.reference_no}
              onChange={(event) => setEditForm((prev) => ({ ...prev, reference_no: event.target.value }))}
              className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-600">หมายเหตุ</label>
            <textarea
              rows={3}
              maxLength={500}
              value={editForm.note}
              onChange={(event) => setEditForm((prev) => ({ ...prev, note: event.target.value }))}
              placeholder={editTarget?.is_masked ? 'กรอกหมายเหตุใหม่เพื่อแทนที่ค่าเดิม (ไม่กรอกจะคงค่าเดิม)' : ''}
              className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm"
            />
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={() => setEditTarget(null)}
              disabled={isUpdating}
              className="rounded-xl border border-slate-200 px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50"
            >
              ปิด
            </button>
            <button
              type="submit"
              disabled={isUpdating}
              className="rounded-xl bg-farm-700 px-4 py-2 text-sm font-semibold text-white hover:bg-farm-800 disabled:opacity-50"
            >
              {isUpdating ? 'กำลังบันทึก...' : 'บันทึกการแก้ไข'}
            </button>
          </div>
        </form>
      </Modal>

      {/* Void Confirmation Modal */}
      <Modal
        isOpen={Boolean(voidTarget)}
        title={`ยืนยันการยกเลิกเอกสาร ${voidTarget?.doc_no || ''}`}
        onClose={() => !isVoiding && setVoidTarget(null)}
      >
        <form onSubmit={handleVoidSubmit} className="space-y-4 text-sm">
          <p className="rounded-xl bg-rose-50 px-3.5 py-2.5 text-xs text-rose-700">
            การยกเลิกเอกสารจะเปลี่ยนสถานะเป็นยกเลิก (Void) และกลับยอดคลังและการเงินที่เกี่ยวข้อง ไม่สามารถย้อนกลับได้
          </p>
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-600">เหตุผลการยกเลิก</label>
            <textarea
              rows={3}
              maxLength={500}
              value={voidReason}
              onChange={(event) => setVoidReason(event.target.value)}
              placeholder="ระบุเหตุผลการยกเลิกเอกสาร (ไม่บังคับ)"
              className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm"
            />
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={() => setVoidTarget(null)}
              disabled={isVoiding}
              className="rounded-xl border border-slate-200 px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50"
            >
              กลับ
            </button>
            <button
              type="submit"
              disabled={isVoiding}
              className="inline-flex items-center gap-1.5 rounded-xl bg-rose-600 px-4 py-2 text-sm font-semibold text-white hover:bg-rose-700 disabled:opacity-50"
            >
              <Ban size={15} />
              {isVoiding ? 'กำลังยกเลิก...' : 'ยืนยันการยกเลิก'}
            </button>
          </div>
        </form>
      </Modal>

      <Toast message={toast} visible={Boolean(toast)} />
    </div>
  );
}

export default TradeDocuments;
