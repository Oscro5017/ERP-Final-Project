import { useCallback, useEffect, useState } from 'react';
import { AlertCircle, Bell, Check, Eye, Lightbulb, X } from 'lucide-react';
import { api } from '../lib/api';
import { formatThaiDateTime } from '../utils/dateUtils';

const PAGE_LIMIT = 50;

const KIND_OPTIONS = [
  { value: '', label: 'ทั้งหมด' },
  { value: 'insight', label: 'ข้อมูลวิเคราะห์' },
  { value: 'recommendation', label: 'คำแนะนำ' },
  { value: 'alert', label: 'การแจ้งเตือน' },
];

const STATUS_OPTIONS = [
  { value: '', label: 'ทั้งหมด' },
  { value: 'new', label: 'ใหม่' },
  { value: 'seen', label: 'อ่านแล้ว' },
  { value: 'dismissed', label: 'ละเว้น' },
  { value: 'done', label: 'เสร็จสิ้น' },
];

const KIND_BADGE_MAP = {
  insight: {
    label: 'ข้อมูลวิเคราะห์',
    className: 'bg-blue-100 text-blue-700',
  },
  recommendation: {
    label: 'คำแนะนำ',
    className: 'bg-green-100 text-green-700',
  },
  alert: {
    label: 'การแจ้งเตือน',
    className: 'bg-red-100 text-red-700',
  },
};

const STATUS_BADGE_MAP = {
  new: {
    label: 'ใหม่',
    className: 'bg-blue-100 text-blue-700',
  },
  seen: {
    label: 'อ่านแล้ว',
    className: 'bg-slate-100 text-slate-700',
  },
  dismissed: {
    label: 'ละเว้น',
    className: 'bg-gray-100 text-gray-600',
  },
  done: {
    label: 'เสร็จสิ้น',
    className: 'bg-green-100 text-green-700',
  },
};

const SEVERITY_MAP = {
  low: {
    label: 'ต่ำ',
    icon: Lightbulb,
    iconClassName: 'bg-sky-50 text-sky-600 border-sky-200',
    badgeClassName: 'bg-sky-100 text-sky-700',
  },
  medium: {
    label: 'ปานกลาง',
    icon: Bell,
    iconClassName: 'bg-amber-50 text-amber-600 border-amber-200',
    badgeClassName: 'bg-amber-100 text-amber-700',
  },
  high: {
    label: 'สูง',
    icon: AlertCircle,
    iconClassName: 'bg-rose-50 text-rose-600 border-rose-200',
    badgeClassName: 'bg-rose-100 text-rose-700',
  },
  critical: {
    label: 'วิกฤต',
    icon: AlertCircle,
    iconClassName: 'bg-red-100 text-red-800 border-red-300',
    badgeClassName: 'bg-red-100 text-red-800',
  },
};

const SOURCE_LABELS = {
  rule: 'กฎระบบ',
  model: 'โมเดลวิเคราะห์',
  manual: 'บันทึกเอง',
};

function truncateBody(text, maxLength = 100) {
  if (!text) return '-';
  if (text.length <= maxLength) return text;
  return `${text.slice(0, maxLength).trimEnd()}…`;
}

function Insights() {
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [kindFilter, setKindFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [offset, setOffset] = useState(0);
  const [expandedIds, setExpandedIds] = useState(() => new Set());
  const [isLoading, setIsLoading] = useState(true);
  const [updatingId, setUpdatingId] = useState(null);
  const [error, setError] = useState('');

  const loadInsights = useCallback(async () => {
    setIsLoading(true);
    setError('');
    try {
      const params = new URLSearchParams({
        kind: kindFilter,
        status: statusFilter,
        limit: String(PAGE_LIMIT),
        offset: String(offset),
      });
      const data = await api(`/insights?${params.toString()}`);
      setItems(Array.isArray(data?.items) ? data.items : []);
      setTotal(typeof data?.total === 'number' ? data.total : 0);
    } catch (err) {
      setError(err.message || 'ไม่สามารถโหลดข้อมูลเชิงลึกได้');
    } finally {
      setIsLoading(false);
    }
  }, [kindFilter, statusFilter, offset]);

  useEffect(() => {
    loadInsights();
  }, [loadInsights]);

  const handleKindChange = (value) => {
    setKindFilter(value);
    setOffset(0);
  };

  const handleStatusChange = (value) => {
    setStatusFilter(value);
    setOffset(0);
  };

  const toggleExpand = (id) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const handleStatusUpdate = async (event, item, nextStatus) => {
    event.stopPropagation();
    if (updatingId === item.id || item.status === nextStatus) return;

    setUpdatingId(item.id);
    setError('');
    try {
      const updated = await api(`/insights/${item.id}/status`, {
        method: 'PATCH',
        body: JSON.stringify({ status: nextStatus }),
      });
      setItems((current) =>
        current.map((entry) =>
          entry.id === item.id
            ? updated && updated.id
              ? updated
              : { ...entry, status: nextStatus }
            : entry
        )
      );
    } catch (err) {
      setError(err.message || 'ไม่สามารถอัปเดตสถานะได้');
    } finally {
      setUpdatingId(null);
    }
  };

  const currentPageStart = total === 0 ? 0 : offset + 1;
  const currentPageEnd = Math.min(offset + items.length, total);
  const hasPrev = offset > 0;
  const hasNext = offset + PAGE_LIMIT < total;

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-slate-800">ข้อมูลเชิงลึก</h1>
          <p className="mt-1 text-sm text-slate-500">คำแนะนำ การแจ้งเตือน และข้อมูลวิเคราะห์</p>
        </div>
        {!isLoading && (
          <span className="inline-flex w-fit items-center rounded-full bg-farm-50 px-3 py-1 text-xs font-semibold text-farm-700">
            ทั้งหมด {total} รายการ
          </span>
        )}
      </div>

      <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-soft">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs font-medium text-slate-500">ประเภท:</span>
            <div className="flex flex-wrap items-center gap-1 rounded-xl bg-slate-100 p-1" role="group" aria-label="กรองตามประเภท">
              {KIND_OPTIONS.map((option) => (
                <button
                  key={option.value || 'all'}
                  type="button"
                  onClick={() => handleKindChange(option.value)}
                  className={`rounded-lg px-3 py-1.5 text-xs font-medium transition ${
                    kindFilter === option.value
                      ? 'bg-white text-farm-800 shadow-sm'
                      : 'text-slate-600 hover:text-slate-800'
                  }`}
                >
                  {option.label}
                </button>
              ))}
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs font-medium text-slate-500">สถานะ:</span>
            <div className="flex flex-wrap items-center gap-1 rounded-xl bg-slate-100 p-1" role="group" aria-label="กรองตามสถานะ">
              {STATUS_OPTIONS.map((option) => (
                <button
                  key={option.value || 'all'}
                  type="button"
                  onClick={() => handleStatusChange(option.value)}
                  className={`rounded-lg px-3 py-1.5 text-xs font-medium transition ${
                    statusFilter === option.value
                      ? 'bg-white text-farm-800 shadow-sm'
                      : 'text-slate-600 hover:text-slate-800'
                  }`}
                >
                  {option.label}
                </button>
              ))}
            </div>
          </div>
        </div>
      </section>

      {error && (
        <div role="alert" className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
          {error}
        </div>
      )}

      {isLoading ? (
        <div className="rounded-2xl border border-slate-200 bg-white p-10 text-center text-sm text-slate-500 shadow-soft">
          กำลังโหลดข้อมูลเชิงลึก…
        </div>
      ) : items.length === 0 ? (
        <div className="rounded-2xl border border-slate-200 bg-white p-12 text-center shadow-soft">
          <Lightbulb size={28} className="mx-auto mb-3 text-slate-400" />
          <p className="text-sm font-medium text-slate-600">ยังไม่มีข้อมูลเชิงลึก</p>
        </div>
      ) : (
        <div className="space-y-3">
          {items.map((item) => {
            const severityInfo = SEVERITY_MAP[item.severity] || SEVERITY_MAP.low;
            const SeverityIcon = severityInfo.icon;
            const kindInfo = KIND_BADGE_MAP[item.kind] || {
              label: item.kind || '-',
              className: 'bg-slate-100 text-slate-700',
            };
            const statusInfo = STATUS_BADGE_MAP[item.status] || {
              label: item.status || '-',
              className: 'bg-slate-100 text-slate-700',
            };
            const isExpanded = expandedIds.has(item.id);
            const isUpdating = updatingId === item.id;
            const maskedClass = item.is_masked ? 'font-mono text-slate-400' : '';

            return (
              <article
                key={item.id}
                onClick={() => toggleExpand(item.id)}
                role="button"
                tabIndex={0}
                aria-expanded={isExpanded}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault();
                    toggleExpand(item.id);
                  }
                }}
                className="cursor-pointer rounded-2xl border border-slate-200 bg-white p-4 shadow-soft transition hover:border-slate-300"
              >
                <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div className="flex min-w-0 items-start gap-3">
                    <div
                      className={`mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border ${severityInfo.iconClassName}`}
                      title={`ระดับความสำคัญ: ${severityInfo.label}`}
                    >
                      <SeverityIcon size={18} />
                    </div>

                    <div className="min-w-0 flex-1 space-y-1.5">
                      <div className="flex flex-wrap items-center gap-2">
                        <h2
                          className={`text-base font-semibold ${
                            item.is_masked ? maskedClass : 'text-slate-800'
                          }`}
                        >
                          {item.title || '-'}
                        </h2>
                        <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${kindInfo.className}`}>
                          {kindInfo.label}
                        </span>
                        <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${statusInfo.className}`}>
                          {statusInfo.label}
                        </span>
                      </div>

                      <p
                        className={`text-sm leading-relaxed ${
                          item.is_masked ? maskedClass : 'text-slate-600'
                        } ${isExpanded ? 'whitespace-pre-wrap' : ''}`}
                      >
                        {isExpanded ? item.body || '-' : truncateBody(item.body, 100)}
                      </p>

                      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 pt-0.5 text-xs text-slate-400">
                        <span>สร้างเมื่อ: {formatThaiDateTime(item.created_at)}</span>
                        <span>{isExpanded ? 'คลิกเพื่อย่อ' : 'คลิกเพื่อดูรายละเอียด'}</span>
                      </div>
                    </div>
                  </div>

                  <div className="flex shrink-0 items-center gap-1.5 self-end sm:self-start">
                    <button
                      type="button"
                      onClick={(event) => handleStatusUpdate(event, item, 'seen')}
                      disabled={isUpdating || item.status === 'seen'}
                      title="ทำเครื่องหมายว่าอ่านแล้ว"
                      aria-label="ทำเครื่องหมายว่าอ่านแล้ว"
                      className={`inline-flex items-center gap-1 rounded-lg border px-2.5 py-1.5 text-xs font-medium transition ${
                        item.status === 'seen'
                          ? 'border-slate-200 bg-slate-100 text-slate-400'
                          : 'border-slate-200 bg-white text-slate-600 hover:bg-slate-50 hover:text-slate-800'
                      } disabled:cursor-not-allowed disabled:opacity-60`}
                    >
                      <Eye size={14} />
                      <span>อ่านแล้ว</span>
                    </button>

                    <button
                      type="button"
                      onClick={(event) => handleStatusUpdate(event, item, 'done')}
                      disabled={isUpdating || item.status === 'done'}
                      title="ทำเครื่องหมายว่าเสร็จสิ้น"
                      aria-label="ทำเครื่องหมายว่าเสร็จสิ้น"
                      className={`inline-flex items-center gap-1 rounded-lg border px-2.5 py-1.5 text-xs font-medium transition ${
                        item.status === 'done'
                          ? 'border-green-200 bg-green-50 text-green-400'
                          : 'border-green-200 bg-white text-green-700 hover:bg-green-50'
                      } disabled:cursor-not-allowed disabled:opacity-60`}
                    >
                      <Check size={14} />
                      <span>เสร็จสิ้น</span>
                    </button>

                    <button
                      type="button"
                      onClick={(event) => handleStatusUpdate(event, item, 'dismissed')}
                      disabled={isUpdating || item.status === 'dismissed'}
                      title="ละเว้นรายการนี้"
                      aria-label="ละเว้นรายการนี้"
                      className={`inline-flex items-center gap-1 rounded-lg border px-2.5 py-1.5 text-xs font-medium transition ${
                        item.status === 'dismissed'
                          ? 'border-gray-200 bg-gray-100 text-gray-400'
                          : 'border-gray-200 bg-white text-gray-600 hover:bg-gray-50 hover:text-gray-800'
                      } disabled:cursor-not-allowed disabled:opacity-60`}
                    >
                      <X size={14} />
                      <span>ละเว้น</span>
                    </button>
                  </div>
                </div>

                {isExpanded && (
                  <div className="mt-4 border-t border-slate-100 pt-3">
                    {item.decrypt_failed && (
                      <p className="mb-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs font-medium text-amber-700">
                        ไม่สามารถถอดรหัสข้อมูลบางส่วนได้
                      </p>
                    )}
                    <dl className="grid gap-x-6 gap-y-2 text-xs sm:grid-cols-2 lg:grid-cols-3">
                      <div className="flex items-center gap-2">
                        <dt className="text-slate-400">ระดับความสำคัญ:</dt>
                        <dd>
                          <span className={`rounded-full px-2 py-0.5 font-medium ${severityInfo.badgeClassName}`}>
                            {severityInfo.label}
                          </span>
                        </dd>
                      </div>
                      <div className="flex items-center gap-2">
                        <dt className="text-slate-400">แหล่งที่มา:</dt>
                        <dd className="font-medium text-slate-700">
                          {SOURCE_LABELS[item.source] || item.source || '-'}
                        </dd>
                      </div>
                      <div className="flex items-center gap-2">
                        <dt className="text-slate-400">อัปเดตล่าสุด:</dt>
                        <dd className="text-slate-700">{formatThaiDateTime(item.updated_at)}</dd>
                      </div>
                      <div className="flex items-center gap-2">
                        <dt className="text-slate-400">มีผลตั้งแต่:</dt>
                        <dd className="text-slate-700">
                          {item.valid_from ? formatThaiDateTime(item.valid_from) : '-'}
                        </dd>
                      </div>
                      <div className="flex items-center gap-2">
                        <dt className="text-slate-400">มีผลถึง:</dt>
                        <dd className="text-slate-700">
                          {item.valid_until ? formatThaiDateTime(item.valid_until) : '-'}
                        </dd>
                      </div>
                      <div className="flex items-center gap-2">
                        <dt className="text-slate-400">รอบปลูก / งาน:</dt>
                        <dd className="text-slate-700">
                          {item.crop_cycle_id ? `รอบ #${item.crop_cycle_id}` : '-'}
                          {item.task_id ? ` · งาน #${item.task_id}` : ''}
                        </dd>
                      </div>
                    </dl>
                  </div>
                )}
              </article>
            );
          })}

          {total > PAGE_LIMIT && (
            <div className="flex items-center justify-between rounded-2xl border border-slate-200 bg-white px-4 py-3 text-xs text-slate-500 shadow-soft">
              <span>
                แสดง {currentPageStart}–{currentPageEnd} จาก {total} รายการ
              </span>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setOffset((prev) => Math.max(0, prev - PAGE_LIMIT))}
                  disabled={!hasPrev || isLoading}
                  className="rounded-lg border border-slate-200 px-3 py-1.5 font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  ก่อนหน้า
                </button>
                <button
                  type="button"
                  onClick={() => setOffset((prev) => prev + PAGE_LIMIT)}
                  disabled={!hasNext || isLoading}
                  className="rounded-lg border border-slate-200 px-3 py-1.5 font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  ถัดไป
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default Insights;
