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
import Modal from '../components/Modal';
import ThaiDateInput from '../components/ThaiDateInput';
import Toast from '../components/Toast';
import { api, getRole } from '../lib/api';
import { formatThaiDate, formatThaiDateTime, getLocalDateString } from '../utils/dateUtils';

const PAGE_LIMIT = 50;

const emptyLine = () => ({
  product_id: '',
  quantity: '1',
  unit: '',
  unit_price: '',
});

const emptyCreateForm = () => ({
  doc_date: getLocalDateString(),
  partner_id: '',
  crop_cycle_id: '',
  reference_no: '',
  note: '',
  lines: [emptyLine()],
});

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

function TradeDocuments() {
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
  const [createForm, setCreateForm] = useState(emptyCreateForm);
  const [isCreating, setIsCreating] = useState(false);

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
    toastTimerRef.current = window.setTimeout(() => setToast(''), 2500);
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

  const openCreateModal = (type) => {
    setCreateDocType(type);
    setCreateForm(emptyCreateForm());
  };

  const closeCreateModal = () => {
    if (isCreating) return;
    setCreateDocType(null);
  };

  const updateLine = (index, field, value) => {
    setCreateForm((prev) => ({
      ...prev,
      lines: prev.lines.map((line, i) => (i === index ? { ...line, [field]: value } : line)),
    }));
  };

  const addLine = () => {
    setCreateForm((prev) => ({
      ...prev,
      lines: [...prev.lines, emptyLine()],
    }));
  };

  const removeLine = (index) => {
    setCreateForm((prev) => {
      if (prev.lines.length <= 1) return prev;
      return {
        ...prev,
        lines: prev.lines.filter((_, i) => i !== index),
      };
    });
  };

  const handleCreateSubmit = async (event) => {
    event.preventDefault();
    if (!createDocType) return;

    const parsedLines = [];
    for (let i = 0; i < createForm.lines.length; i += 1) {
      const line = createForm.lines[i];
      const productId = Number(line.product_id);
      const quantity = Number(line.quantity);
      if (!Number.isInteger(productId) || productId <= 0) {
        showToast(`รายการที่ ${i + 1}: กรุณากรอกรหัสสินค้าเป็นจำนวนเต็มบวก`);
        return;
      }
      if (!Number.isFinite(quantity) || quantity <= 0) {
        showToast(`รายการที่ ${i + 1}: กรุณากรอกจำนวนที่มากกว่า 0`);
        return;
      }
      const linePayload = {
        product_id: productId,
        quantity,
      };
      if (line.unit.trim()) linePayload.unit = line.unit.trim();
      if (line.unit_price !== '') {
        const unitPrice = Number(line.unit_price);
        if (!Number.isFinite(unitPrice) || unitPrice < 0) {
          showToast(`รายการที่ ${i + 1}: ราคาต่อหน่วยต้องไม่ติดลบ`);
          return;
        }
        linePayload.unit_price = unitPrice;
      }
      parsedLines.push(linePayload);
    }

    const payload = {
      lines: parsedLines,
    };
    if (createForm.doc_date) payload.doc_date = createForm.doc_date;
    if (createForm.partner_id !== '') {
      const partnerId = Number(createForm.partner_id);
      if (!Number.isInteger(partnerId) || partnerId <= 0) {
        showToast(
          createDocType === 'inbound'
            ? 'รหัสซัพพลายเออร์ต้องเป็นจำนวนเต็มบวก'
            : 'รหัสลูกค้าต้องเป็นจำนวนเต็มบวก'
        );
        return;
      }
      if (createDocType === 'inbound') payload.supplier_id = partnerId;
      else payload.customer_id = partnerId;
    }
    if (createForm.crop_cycle_id !== '') {
      const cycleId = Number(createForm.crop_cycle_id);
      if (!Number.isInteger(cycleId) || cycleId <= 0) {
        showToast('รหัสรอบปลูกต้องเป็นจำนวนเต็มบวก');
        return;
      }
      payload.crop_cycle_id = cycleId;
    }
    if (createForm.reference_no.trim()) payload.reference_no = createForm.reference_no.trim();
    if (createForm.note.trim()) payload.note = createForm.note.trim();

    setIsCreating(true);
    try {
      const endpoint = createDocType === 'inbound' ? '/trade/inbound' : '/trade/outbound';
      const created = await api(endpoint, {
        method: 'POST',
        body: JSON.stringify(payload),
      });
      setCreateDocType(null);
      showToast(`สร้างเอกสาร ${created.doc_no} สำเร็จ`);
      setExpandedIds((prev) => ({ ...prev, [created.id]: true }));
      await loadDocuments(0);
      setOffset(0);
    } catch (err) {
      showToast(err.message);
    } finally {
      setIsCreating(false);
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

  const estimatedCreateTotal = createForm.lines.reduce((sum, line) => {
    const qty = Number(line.quantity);
    const price = Number(line.unit_price);
    if (line.unit_price === '' || !Number.isFinite(qty) || !Number.isFinite(price)) return sum;
    return sum + qty * price;
  }, 0);

  const hasCreatePrices = createForm.lines.some((line) => line.unit_price !== '');

  const getPartnerDisplay = (doc) => {
    const isVoid = doc.status === 'void';
    if (doc.doc_type === 'inbound') {
      if (doc.supplier_name) {
        return <MaskedText value={doc.supplier_name} isMasked={doc.is_masked} strikethrough={isVoid} />;
      }
      if (doc.supplier_id) {
        return <span className={isVoid ? 'line-through' : ''}>ซัพพลายเออร์ #{doc.supplier_id}</span>;
      }
      return <span className="text-slate-400">-</span>;
    }
    if (doc.customer_name) {
      return <MaskedText value={doc.customer_name} isMasked={doc.is_masked} strikethrough={isVoid} />;
    }
    if (doc.customer_id) {
      return <span className={isVoid ? 'line-through' : ''}>ลูกค้า #{doc.customer_id}</span>;
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
            <h1 className="text-2xl font-semibold text-slate-800">เอกสารซื้อขาย</h1>
          </div>
          <p className="mt-1 text-sm text-slate-500">จัดการเอกสารรับเข้าวัตถุดิบและส่งออกผลผลิต</p>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          <button
            type="button"
            onClick={() => openCreateModal('inbound')}
            className="inline-flex items-center gap-2 rounded-xl bg-farm-700 px-4 py-2.5 text-sm font-semibold text-white shadow-soft transition hover:bg-farm-800"
          >
            <Plus size={16} />
            <ArrowDownToLine size={16} />
            รับเข้า
          </button>
          <button
            type="button"
            onClick={() => openCreateModal('outbound')}
            className="inline-flex items-center gap-2 rounded-xl border border-farm-700 bg-white px-4 py-2.5 text-sm font-semibold text-farm-700 shadow-soft transition hover:bg-farm-50"
          >
            <Plus size={16} />
            <ArrowUpFromLine size={16} />
            ส่งออก
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
          <div className="inline-flex rounded-xl bg-slate-100 p-1" role="tablist" aria-label="ประเภทเอกสาร">
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
                <th className="px-4 py-3 font-semibold">สถานะ</th>
                <th className="px-4 py-3 text-right font-semibold">จัดการ</th>
              </tr>
            </thead>
            <tbody>
              {isLoading && (
                <tr>
                  <td colSpan={7} className="px-4 py-10 text-center text-slate-500">
                    กำลังโหลดข้อมูลเอกสาร...
                  </td>
                </tr>
              )}
              {!isLoading && documents.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-4 py-12 text-center text-slate-500">
                    ไม่พบเอกสารซื้อขายตามเงื่อนไขที่เลือก
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
                          <div className={isVoid ? 'text-slate-400 line-through' : 'text-slate-800'}>
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
                            <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2.5 py-1 text-xs font-semibold text-emerald-700">
                              <ArrowDownToLine size={12} />
                              รับเข้า
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1 rounded-full bg-sky-100 px-2.5 py-1 text-xs font-semibold text-sky-700">
                              <ArrowUpFromLine size={12} />
                              ส่งออก
                            </span>
                          )}
                        </td>
                        <td className={`px-4 py-3 ${isVoid ? 'text-slate-400 line-through' : 'text-slate-700'}`}>
                          {formatThaiDate(doc.doc_date)}
                        </td>
                        <td className={`px-4 py-3 ${isVoid ? 'text-slate-400' : 'text-slate-700'}`}>
                          {getPartnerDisplay(doc)}
                        </td>
                        <td className="px-4 py-3">
                          <div className="space-y-1">
                            {isVoid ? (
                              <span className="inline-flex items-center gap-1 rounded-full bg-rose-100 px-2.5 py-1 text-xs font-semibold text-rose-700 line-through">
                                ยกเลิกแล้ว
                              </span>
                            ) : (
                              <span className="inline-flex items-center rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-semibold text-emerald-700">
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
                              className="inline-flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-100"
                              title="ดูรายละเอียด"
                              aria-label={`ดูรายละเอียด ${doc.doc_no}`}
                            >
                              <Eye size={14} />
                              <span className="hidden sm:inline">{isExpanded ? 'ซ่อน' : 'ดูรายการ'}</span>
                            </button>
                            {!isVoid && (
                              <button
                                type="button"
                                onClick={() => openVoidModal(doc)}
                                className="inline-flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-xs font-medium text-rose-600 hover:bg-rose-50"
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
                          <td colSpan={7} className="px-6 py-4">
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
                                    <span className="text-slate-400">รอบปลูก ID: </span>
                                    <span className="font-medium text-slate-700">{doc.crop_cycle_id || '-'}</span>
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
                                      คำเตือน: {doc.warnings.join(', ')}
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
                                      <th className="px-3 py-2 font-semibold">รหัสสินค้า</th>
                                      <th className="px-3 py-2 font-semibold">ชื่อสินค้า</th>
                                      <th className="px-3 py-2 text-right font-semibold">จำนวน</th>
                                      <th className="px-3 py-2 font-semibold">หน่วย</th>
                                      <th className="px-3 py-2 text-right font-semibold">ราคา/หน่วย</th>
                                      <th className="px-3 py-2 text-right font-semibold">รวมเป็นเงิน</th>
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {(!doc.lines || doc.lines.length === 0) && (
                                      <tr>
                                        <td colSpan={7} className="px-3 py-4 text-center text-slate-400">
                                          ไม่มีรายการสินค้า
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
                                          <td className="px-3 py-2">{line.product_id}</td>
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

      {/* Create Inbound / Outbound Modal */}
      <Modal
        isOpen={Boolean(createDocType)}
        title={createDocType === 'inbound' ? 'สร้างเอกสารรับเข้าวัตถุดิบ' : 'สร้างเอกสารส่งออกผลผลิต'}
        onClose={closeCreateModal}
      >
        <form onSubmit={handleCreateSubmit} className="max-h-[75vh] space-y-4 overflow-y-auto pr-1 text-sm">
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-600">วันที่เอกสาร</label>
              <ThaiDateInput
                value={createForm.doc_date}
                onChange={(val) => setCreateForm((prev) => ({ ...prev, doc_date: val }))}
                label="วันที่เอกสาร"
              />
            </div>

            <div>
              <label className="mb-1 block text-xs font-medium text-slate-600">
                {createDocType === 'inbound' ? 'รหัสซัพพลายเออร์ (ID)' : 'รหัสลูกค้า (ID)'}
              </label>
              <input
                type="number"
                min="1"
                step="1"
                value={createForm.partner_id}
                onChange={(event) => setCreateForm((prev) => ({ ...prev, partner_id: event.target.value }))}
                placeholder={createDocType === 'inbound' ? 'ระบุ ID ซัพพลายเออร์ (ไม่บังคับ)' : 'ระบุ ID ลูกค้า (ไม่บังคับ)'}
                className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm"
              />
            </div>

            <div>
              <label className="mb-1 block text-xs font-medium text-slate-600">เลขที่อ้างอิง</label>
              <input
                type="text"
                maxLength={120}
                value={createForm.reference_no}
                onChange={(event) => setCreateForm((prev) => ({ ...prev, reference_no: event.target.value }))}
                placeholder="เช่น INV-001"
                className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm"
              />
            </div>

            <div>
              <label className="mb-1 block text-xs font-medium text-slate-600">รหัสรอบปลูก (ID)</label>
              <input
                type="number"
                min="1"
                step="1"
                value={createForm.crop_cycle_id}
                onChange={(event) => setCreateForm((prev) => ({ ...prev, crop_cycle_id: event.target.value }))}
                placeholder="ไม่บังคับ"
                className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm"
              />
            </div>
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-slate-600">หมายเหตุ</label>
            <textarea
              rows={2}
              maxLength={500}
              value={createForm.note}
              onChange={(event) => setCreateForm((prev) => ({ ...prev, note: event.target.value }))}
              placeholder="รายละเอียดเพิ่มเติม..."
              className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm"
            />
          </div>

          <div className="space-y-2.5 border-t border-slate-100 pt-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-slate-700">รายการสินค้า</span>
              <button
                type="button"
                onClick={addLine}
                className="inline-flex items-center gap-1 rounded-lg bg-farm-50 px-2.5 py-1 text-xs font-semibold text-farm-700 hover:bg-farm-100"
              >
                <Plus size={14} />
                เพิ่มรายการ
              </button>
            </div>

            <div className="space-y-2.5">
              {createForm.lines.map((line, index) => {
                const qty = Number(line.quantity);
                const price = Number(line.unit_price);
                const lineSubtotal =
                  line.unit_price !== '' && Number.isFinite(qty) && Number.isFinite(price)
                    ? qty * price
                    : null;

                return (
                  <div key={index} className="rounded-xl border border-slate-200 bg-slate-50/70 p-3 space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-medium text-slate-500">รายการที่ {index + 1}</span>
                      {createForm.lines.length > 1 && (
                        <button
                          type="button"
                          onClick={() => removeLine(index)}
                          className="text-xs font-medium text-rose-600 hover:underline"
                        >
                          ลบรายการ
                        </button>
                      )}
                    </div>
                    <div className="grid gap-2 sm:grid-cols-4">
                      <div>
                        <label className="mb-1 block text-[11px] text-slate-500">รหัสสินค้า (ID) *</label>
                        <input
                          type="number"
                          min="1"
                          step="1"
                          required
                          value={line.product_id}
                          onChange={(event) => updateLine(index, 'product_id', event.target.value)}
                          placeholder="Product ID"
                          className="w-full rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-sm"
                        />
                      </div>
                      <div>
                        <label className="mb-1 block text-[11px] text-slate-500">จำนวน *</label>
                        <input
                          type="number"
                          min="0.001"
                          step="any"
                          required
                          value={line.quantity}
                          onChange={(event) => updateLine(index, 'quantity', event.target.value)}
                          className="w-full rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-sm"
                        />
                      </div>
                      <div>
                        <label className="mb-1 block text-[11px] text-slate-500">หน่วย</label>
                        <input
                          type="text"
                          maxLength={80}
                          value={line.unit}
                          onChange={(event) => updateLine(index, 'unit', event.target.value)}
                          placeholder="ค่าเริ่มต้นสินค้า"
                          className="w-full rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-sm"
                        />
                      </div>
                      <div>
                        <label className="mb-1 block text-[11px] text-slate-500">ราคาต่อหน่วย</label>
                        <input
                          type="number"
                          min="0"
                          step="0.01"
                          value={line.unit_price}
                          onChange={(event) => updateLine(index, 'unit_price', event.target.value)}
                          placeholder="0.00"
                          className="w-full rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-sm"
                        />
                      </div>
                    </div>
                    {lineSubtotal !== null && (
                      <div className="text-right text-xs text-slate-500">
                        รวมรายการ: <span className="font-semibold text-slate-700">{formatNumber(lineSubtotal)} บาท</span>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>

            {hasCreatePrices && (
              <div className="flex justify-end rounded-xl bg-farm-50 px-3 py-2 text-sm font-semibold text-farm-800">
                ยอดรวมประมาณการ: {formatNumber(estimatedCreateTotal)} บาท
              </div>
            )}
          </div>

          <div className="flex justify-end gap-2 border-t border-slate-100 pt-3">
            <button
              type="button"
              onClick={closeCreateModal}
              disabled={isCreating}
              className="rounded-xl border border-slate-200 px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50"
            >
              ยกเลิก
            </button>
            <button
              type="submit"
              disabled={isCreating}
              className="inline-flex items-center gap-2 rounded-xl bg-farm-700 px-4 py-2 text-sm font-semibold text-white hover:bg-farm-800 disabled:opacity-50"
            >
              {isCreating ? 'กำลังบันทึก...' : 'บันทึกเอกสาร'}
            </button>
          </div>
        </form>
      </Modal>

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
            การยกเลิกเอกสารจะเปลี่ยนสถานะเป็นยกเลิก (Void) และกลับรายการเคลื่อนไหวสินค้าและการเงินที่เกี่ยวข้อง ไม่สามารถย้อนกลับได้
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
