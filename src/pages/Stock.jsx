import { useCallback, useEffect, useState } from 'react';
import { ArrowUpDown, Calendar, Filter, Package } from 'lucide-react';
import ThaiDateInput from '../components/ThaiDateInput';
import { api } from '../lib/api';
import { formatThaiDate, formatThaiDateTime, getLocalDateString } from '../utils/dateUtils';

const BALANCES_LIMIT = 200;
const MOVEMENTS_LIMIT = 50;

const MOVEMENT_TYPE_LABELS = {
  inbound: 'รับเข้า',
  outbound: 'ส่งออก',
  adjustment: 'ปรับยอด',
  harvest_in: 'เก็บเกี่ยว',
  input_out: 'ใช้วัตถุดิบ',
};

const MOVEMENT_TYPE_STYLES = {
  inbound: 'bg-emerald-100 text-emerald-700',
  outbound: 'bg-rose-100 text-rose-700',
  adjustment: 'bg-amber-100 text-amber-700',
  harvest_in: 'bg-green-100 text-green-700',
  input_out: 'bg-sky-100 text-sky-700',
};

const MOVEMENT_TYPE_OPTIONS = Object.entries(MOVEMENT_TYPE_LABELS);

const SOURCE_TYPE_LABELS = {
  stock_receipt: 'ใบรับเข้า',
  stock_issue: 'ใบเบิกจ่าย',
  stock_document: 'เอกสารคลัง',
  harvest: 'การเก็บเกี่ยว',
  input_application: 'การใช้วัตถุดิบ',
  adjustment: 'ปรับยอดสต็อก',
  manual: 'บันทึกด้วยตนเอง',
};

function formatNumber(value) {
  const num = Number(value ?? 0);
  if (Number.isNaN(num)) return '-';
  return num.toLocaleString('th-TH', { maximumFractionDigits: 3 });
}

function formatSource(sourceType, sourceId) {
  if (!sourceType && !sourceId) return '-';
  const label = SOURCE_TYPE_LABELS[sourceType] || sourceType || 'ระบบ';
  return sourceId ? `${label} #${sourceId}` : label;
}

function Stock() {
  const [activeTab, setActiveTab] = useState('balances');

  // Balances state
  const [balances, setBalances] = useState([]);
  const [balancesTotal, setBalancesTotal] = useState(0);
  const [balancesOffset, setBalancesOffset] = useState(0);
  const [balanceProductId, setBalanceProductId] = useState('');
  const [asOfDate, setAsOfDate] = useState('');
  const [balancesLoading, setBalancesLoading] = useState(true);
  const [balancesError, setBalancesError] = useState('');

  // Product lookup for dropdown & movement display
  const [productOptions, setProductOptions] = useState([]);

  // Movements state
  const [movements, setMovements] = useState([]);
  const [movementsTotal, setMovementsTotal] = useState(0);
  const [movementsOffset, setMovementsOffset] = useState(0);
  const [movementProductId, setMovementProductId] = useState('');
  const [fromDate, setFromDate] = useState('');
  const [toDate, setToDate] = useState('');
  const [movementType, setMovementType] = useState('');
  const [includeVoid, setIncludeVoid] = useState(false);
  const [movementsLoading, setMovementsLoading] = useState(false);
  const [movementsError, setMovementsError] = useState('');

  const invalidDateRange = Boolean(fromDate && toDate && fromDate > toDate);

  const loadBalances = useCallback(async ({
    productId = balanceProductId,
    asOf = asOfDate,
    offset = balancesOffset,
  } = {}) => {
    setBalancesLoading(true);
    setBalancesError('');
    try {
      const params = new URLSearchParams({
        limit: String(BALANCES_LIMIT),
        offset: String(offset),
      });
      if (productId) params.set('product_id', String(productId));
      if (asOf) params.set('as_of', asOf);

      const data = await api(`/stock/balances?${params.toString()}`);
      const items = data?.items || [];
      setBalances(items);
      setBalancesTotal(Number(data?.total ?? items.length));

      if (!productId && offset === 0) {
        setProductOptions(items);
      }
    } catch (error) {
      setBalancesError(error.message || 'ไม่สามารถโหลดยอดคงเหลือสินค้าได้');
    } finally {
      setBalancesLoading(false);
    }
  }, [asOfDate, balanceProductId, balancesOffset]);

  const loadMovements = useCallback(async ({
    productId = movementProductId,
    from = fromDate,
    to = toDate,
    type = movementType,
    voided = includeVoid,
    offset = movementsOffset,
  } = {}) => {
    if (from && to && from > to) {
      setMovementsError('วันที่เริ่มต้นต้องไม่อยู่หลังวันที่สิ้นสุด');
      return;
    }

    setMovementsLoading(true);
    setMovementsError('');
    try {
      const params = new URLSearchParams({
        include_void: String(Boolean(voided)),
        limit: String(MOVEMENTS_LIMIT),
        offset: String(offset),
      });
      if (productId) params.set('product_id', String(productId));
      if (from) params.set('from', from);
      if (to) params.set('to', to);
      if (type) params.set('movement_type', type);

      const data = await api(`/stock/movements?${params.toString()}`);
      const items = data?.items || [];
      setMovements(items);
      setMovementsTotal(Number(data?.total ?? items.length));
    } catch (error) {
      setMovementsError(error.message || 'ไม่สามารถโหลดประวัติเคลื่อนไหวสินค้าได้');
    } finally {
      setMovementsLoading(false);
    }
  }, [fromDate, includeVoid, movementProductId, movementType, movementsOffset, toDate]);

  useEffect(() => {
    if (activeTab === 'balances') {
      loadBalances();
    } else {
      loadMovements();
    }
  }, [activeTab, loadBalances, loadMovements]);

  const handleBalanceFilterSubmit = (event) => {
    event.preventDefault();
    if (balancesOffset !== 0) {
      setBalancesOffset(0);
    } else {
      loadBalances({ offset: 0 });
    }
  };

  const handleClearBalanceFilters = () => {
    setBalanceProductId('');
    setAsOfDate('');
    setBalancesOffset(0);
  };

  const handleMovementFilterSubmit = (event) => {
    event.preventDefault();
    if (invalidDateRange) return;
    if (movementsOffset !== 0) {
      setMovementsOffset(0);
    } else {
      loadMovements({ offset: 0 });
    }
  };

  const handleClearMovementFilters = () => {
    setMovementProductId('');
    setFromDate('');
    setToDate('');
    setMovementType('');
    setIncludeVoid(false);
    setMovementsOffset(0);
  };

  const displayedAsOf = balances[0]?.as_of || asOfDate || getLocalDateString();

  const productById = productOptions.reduce((acc, item) => {
    acc[item.product_id] = item;
    return acc;
  }, {});

  const balancesPageStart = balancesTotal === 0 ? 0 : balancesOffset + 1;
  const balancesPageEnd = Math.min(balancesOffset + balances.length, balancesTotal);

  const movementsPageStart = movementsTotal === 0 ? 0 : movementsOffset + 1;
  const movementsPageEnd = Math.min(movementsOffset + movements.length, movementsTotal);

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div className="flex items-start gap-3">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-farm-100 text-farm-700">
            <Package size={22} />
          </div>
          <div>
            <h1 className="text-2xl font-semibold text-slate-800">คลังสินค้า</h1>
            <p className="text-sm text-slate-500">ดูยอดคงเหลือและประวัติการเคลื่อนไหวสินค้า</p>
          </div>
        </div>

        <div className="inline-flex items-center gap-1 rounded-2xl border border-slate-200 bg-white p-1 shadow-soft">
          <button
            type="button"
            onClick={() => setActiveTab('balances')}
            className={`inline-flex items-center gap-2 rounded-xl px-4 py-2 text-sm font-semibold transition ${
              activeTab === 'balances'
                ? 'bg-farm-700 text-white shadow-sm'
                : 'text-slate-600 hover:bg-slate-100'
            }`}
          >
            <Package size={16} />
            ยอดคงเหลือ
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('movements')}
            className={`inline-flex items-center gap-2 rounded-xl px-4 py-2 text-sm font-semibold transition ${
              activeTab === 'movements'
                ? 'bg-farm-700 text-white shadow-sm'
                : 'text-slate-600 hover:bg-slate-100'
            }`}
          >
            <ArrowUpDown size={16} />
            ประวัติเคลื่อนไหว
          </button>
        </div>
      </div>

      {activeTab === 'balances' && (
        <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-soft">
          <div className="flex flex-col gap-3 border-b border-slate-100 p-5 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex flex-wrap items-center gap-3">
              <h2 className="text-lg font-semibold text-slate-800">ยอดคงเหลือสินค้า</h2>
              <span className="inline-flex items-center gap-1.5 rounded-full bg-farm-50 px-3 py-1 text-xs font-medium text-farm-800">
                <Calendar size={14} />
                ณ วันที่ {formatThaiDate(displayedAsOf)}
              </span>
            </div>
            <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-600">
              ทั้งหมด {formatNumber(balancesTotal)} รายการ
            </span>
          </div>

          <form
            onSubmit={handleBalanceFilterSubmit}
            className="grid gap-3 border-b border-slate-100 bg-slate-50/70 p-4 md:grid-cols-[1fr_220px_auto_auto] md:items-end"
          >
            <label className="flex flex-col gap-1 text-xs font-medium text-slate-600">
              <span className="inline-flex items-center gap-1">
                <Filter size={13} />
                สินค้า
              </span>
              <select
                value={balanceProductId}
                onChange={(event) => {
                  setBalanceProductId(event.target.value);
                  setBalancesOffset(0);
                }}
                className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 outline-none focus:border-farm-700"
              >
                <option value="">สินค้าทั้งหมด</option>
                {productOptions.map((item) => (
                  <option key={item.product_id} value={String(item.product_id)}>
                    {item.is_masked
                      ? `สินค้า #${item.product_id} (เข้ารหัส)`
                      : `${item.product_name} (${item.unit})`}
                  </option>
                ))}
              </select>
            </label>

            <label className="flex flex-col gap-1 text-xs font-medium text-slate-600">
              <span className="inline-flex items-center gap-1">
                <Calendar size={13} />
                ยอดคงเหลือ ณ วันที่
              </span>
              <ThaiDateInput
                value={asOfDate}
                onChange={(value) => {
                  setAsOfDate(value);
                  setBalancesOffset(0);
                }}
                label="ยอดคงเหลือ ณ วันที่"
                className="text-sm"
              />
            </label>

            <button
              type="submit"
              disabled={balancesLoading}
              className="rounded-xl bg-farm-700 px-4 py-2 text-sm font-semibold text-white transition hover:bg-farm-800 disabled:opacity-50"
            >
              ค้นหา
            </button>

            <button
              type="button"
              onClick={handleClearBalanceFilters}
              disabled={balancesLoading}
              className="rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-600 transition hover:bg-slate-100 disabled:opacity-50"
            >
              ล้างตัวกรอง
            </button>
          </form>

          {balancesError ? (
            <div className="m-5 rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700" role="alert">
              {balancesError}
            </div>
          ) : balancesLoading ? (
            <div className="p-10 text-center text-sm text-slate-500">กำลังโหลดยอดคงเหลือสินค้า...</div>
          ) : balances.length === 0 ? (
            <div className="p-10 text-center">
              <Package className="mx-auto mb-2 text-slate-400" size={24} />
              <p className="font-medium text-slate-700">ไม่พบข้อมูลยอดคงเหลือสินค้า</p>
              <p className="mt-1 text-sm text-slate-500">ลองเปลี่ยนตัวกรองสินค้าหรือวันที่ตรวจสอบ</p>
            </div>
          ) : (
            <>
              <div className="overflow-x-auto">
                <table className="min-w-full text-left text-sm">
                  <thead className="bg-slate-50 text-slate-600">
                    <tr>
                      <th scope="col" className="px-4 py-3 font-semibold">สินค้า</th>
                      <th scope="col" className="px-4 py-3 font-semibold">หน่วย</th>
                      <th scope="col" className="px-4 py-3 text-right font-semibold">จำนวน</th>
                      <th scope="col" className="px-4 py-3 font-semibold">สถานะ</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {balances.map((item) => {
                      const isNegative = Boolean(item.negative || Number(item.quantity) < 0);
                      const isZero = !isNegative && Number(item.quantity) === 0;

                      return (
                        <tr key={item.product_id} className="hover:bg-slate-50/70">
                          <td className="px-4 py-3">
                            {item.is_masked ? (
                              <span className="font-mono text-slate-400">
                                {item.product_name || 'ข้อมูลเข้ารหัส'}
                              </span>
                            ) : (
                              <span className="font-medium text-slate-800">{item.product_name}</span>
                            )}
                            {item.decrypt_failed && (
                              <span className="ml-2 rounded bg-rose-50 px-1.5 py-0.5 text-[11px] font-medium text-rose-600">
                                ถอดรหัสไม่สำเร็จ
                              </span>
                            )}
                          </td>
                          <td className="px-4 py-3 text-slate-600">{item.unit || '-'}</td>
                          <td
                            className={`px-4 py-3 text-right tabular-nums font-semibold ${
                              isNegative ? 'text-red-600' : 'text-slate-800'
                            }`}
                          >
                            {formatNumber(item.quantity)}
                          </td>
                          <td className="px-4 py-3">
                            {isNegative ? (
                              <span className="inline-flex rounded-full bg-rose-100 px-3 py-1 text-xs font-semibold text-rose-700">
                                ติดลบ
                              </span>
                            ) : isZero ? (
                              <span className="inline-flex rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-600">
                                หมด
                              </span>
                            ) : (
                              <span className="inline-flex rounded-full bg-emerald-100 px-3 py-1 text-xs font-semibold text-emerald-700">
                                ปกติ
                              </span>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              {balancesTotal > BALANCES_LIMIT && (
                <div className="flex flex-col gap-2 border-t border-slate-100 px-4 py-3 text-xs text-slate-500 sm:flex-row sm:items-center sm:justify-between">
                  <span>
                    แสดง {balancesPageStart}–{balancesPageEnd} จาก {balancesTotal} รายการ
                  </span>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      disabled={balancesOffset === 0 || balancesLoading}
                      onClick={() => setBalancesOffset((prev) => Math.max(0, prev - BALANCES_LIMIT))}
                      className="rounded-lg border border-slate-200 px-3 py-1.5 font-medium text-slate-600 hover:bg-slate-50 disabled:opacity-40"
                    >
                      ก่อนหน้า
                    </button>
                    <button
                      type="button"
                      disabled={balancesOffset + BALANCES_LIMIT >= balancesTotal || balancesLoading}
                      onClick={() => setBalancesOffset((prev) => prev + BALANCES_LIMIT)}
                      className="rounded-lg border border-slate-200 px-3 py-1.5 font-medium text-slate-600 hover:bg-slate-50 disabled:opacity-40"
                    >
                      ถัดไป
                    </button>
                  </div>
                </div>
              )}
            </>
          )}
        </section>
      )}

      {activeTab === 'movements' && (
        <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-soft">
          <div className="flex flex-col gap-3 border-b border-slate-100 p-5 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-2">
              <ArrowUpDown size={18} className="text-farm-700" />
              <h2 className="text-lg font-semibold text-slate-800">ประวัติการเคลื่อนไหวสินค้า</h2>
            </div>
            <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-600">
              ทั้งหมด {formatNumber(movementsTotal)} รายการ
            </span>
          </div>

          <form
            onSubmit={handleMovementFilterSubmit}
            className="space-y-3 border-b border-slate-100 bg-slate-50/70 p-4"
          >
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-[1fr_1fr_1fr_1fr_auto_auto] xl:items-end">
              <label className="flex flex-col gap-1 text-xs font-medium text-slate-600">
                <span className="inline-flex items-center gap-1">
                  <Calendar size={13} />
                  ตั้งแต่วันที่
                </span>
                <ThaiDateInput
                  value={fromDate}
                  onChange={(value) => {
                    setFromDate(value);
                    setMovementsOffset(0);
                  }}
                  label="ตั้งแต่วันที่"
                  className="text-sm"
                />
              </label>

              <label className="flex flex-col gap-1 text-xs font-medium text-slate-600">
                <span className="inline-flex items-center gap-1">
                  <Calendar size={13} />
                  ถึงวันที่
                </span>
                <ThaiDateInput
                  value={toDate}
                  onChange={(value) => {
                    setToDate(value);
                    setMovementsOffset(0);
                  }}
                  label="ถึงวันที่"
                  className="text-sm"
                />
              </label>

              <label className="flex flex-col gap-1 text-xs font-medium text-slate-600">
                <span className="inline-flex items-center gap-1">
                  <Filter size={13} />
                  ประเภทการเคลื่อนไหว
                </span>
                <select
                  value={movementType}
                  onChange={(event) => {
                    setMovementType(event.target.value);
                    setMovementsOffset(0);
                  }}
                  className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 outline-none focus:border-farm-700"
                >
                  <option value="">ทุกประเภท</option>
                  {MOVEMENT_TYPE_OPTIONS.map(([value, label]) => (
                    <option key={value} value={value}>{label}</option>
                  ))}
                </select>
              </label>

              <label className="flex flex-col gap-1 text-xs font-medium text-slate-600">
                <span className="inline-flex items-center gap-1">
                  <Package size={13} />
                  สินค้า
                </span>
                <select
                  value={movementProductId}
                  onChange={(event) => {
                    setMovementProductId(event.target.value);
                    setMovementsOffset(0);
                  }}
                  className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 outline-none focus:border-farm-700"
                >
                  <option value="">สินค้าทั้งหมด</option>
                  {productOptions.map((item) => (
                    <option key={item.product_id} value={String(item.product_id)}>
                      {item.is_masked
                        ? `สินค้า #${item.product_id} (เข้ารหัส)`
                        : `${item.product_name} (${item.unit})`}
                    </option>
                  ))}
                </select>
              </label>

              <button
                type="submit"
                disabled={movementsLoading || invalidDateRange}
                className="rounded-xl bg-farm-700 px-4 py-2 text-sm font-semibold text-white transition hover:bg-farm-800 disabled:cursor-not-allowed disabled:opacity-50"
              >
                กรองข้อมูล
              </button>

              <button
                type="button"
                onClick={handleClearMovementFilters}
                disabled={movementsLoading}
                className="rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-600 transition hover:bg-slate-100 disabled:opacity-50"
              >
                ล้างตัวกรอง
              </button>
            </div>

            <div className="flex flex-wrap items-center justify-between gap-2">
              <label className="inline-flex cursor-pointer items-center gap-2 text-xs font-medium text-slate-600">
                <input
                  type="checkbox"
                  checked={includeVoid}
                  onChange={(event) => {
                    setIncludeVoid(event.target.checked);
                    setMovementsOffset(0);
                  }}
                  className="h-4 w-4 rounded border-slate-300 text-farm-700 focus:ring-farm-600"
                />
                แสดงรายการที่ยกเลิกแล้ว
              </label>

              {invalidDateRange && (
                <p className="text-xs font-medium text-rose-600">
                  วันที่เริ่มต้นต้องไม่อยู่หลังวันที่สิ้นสุด
                </p>
              )}
            </div>
          </form>

          {movementsError ? (
            <div className="m-5 rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700" role="alert">
              {movementsError}
            </div>
          ) : movementsLoading ? (
            <div className="p-10 text-center text-sm text-slate-500">กำลังโหลดประวัติเคลื่อนไหวสินค้า...</div>
          ) : movements.length === 0 ? (
            <div className="p-10 text-center">
              <ArrowUpDown className="mx-auto mb-2 text-slate-400" size={24} />
              <p className="font-medium text-slate-700">ไม่พบประวัติการเคลื่อนไหวสินค้า</p>
              <p className="mt-1 text-sm text-slate-500">ลองปรับช่วงวันที่หรือประเภทการเคลื่อนไหว</p>
            </div>
          ) : (
            <>
              <div className="overflow-x-auto">
                <table className="min-w-full text-left text-sm">
                  <thead className="bg-slate-50 text-slate-600">
                    <tr>
                      <th scope="col" className="px-4 py-3 font-semibold">วันที่</th>
                      <th scope="col" className="px-4 py-3 text-right font-semibold">จำนวน</th>
                      <th scope="col" className="px-4 py-3 font-semibold">ประเภท</th>
                      <th scope="col" className="px-4 py-3 font-semibold">ที่มา</th>
                      <th scope="col" className="px-4 py-3 font-semibold">หมายเหตุ</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {movements.map((item) => {
                      const delta = Number(item.quantity_delta ?? 0);
                      const isPositive = delta > 0;
                      const isNegative = delta < 0;
                      const isVoided = Boolean(item.voided);
                      const typeLabel = MOVEMENT_TYPE_LABELS[item.movement_type] || item.movement_type;
                      const typeStyle = MOVEMENT_TYPE_STYLES[item.movement_type] || 'bg-slate-100 text-slate-700';
                      const product = productById[item.product_id];

                      const deltaColorClass = isVoided
                        ? 'text-slate-400 line-through'
                        : isPositive
                          ? 'text-green-600'
                          : isNegative
                            ? 'text-red-600'
                            : 'text-slate-600';

                      return (
                        <tr
                          key={item.id}
                          className={
                            isVoided
                              ? 'bg-slate-50/70 text-slate-400 line-through'
                              : 'hover:bg-slate-50/70'
                          }
                        >
                          <td className="whitespace-nowrap px-4 py-3">
                            <div className={isVoided ? 'text-slate-400 line-through' : 'font-medium text-slate-700'}>
                              {formatThaiDateTime(item.occurred_at)}
                            </div>
                            {product && (
                              <div className={`mt-0.5 text-xs ${product.is_masked ? 'font-mono text-slate-400' : 'text-slate-500'}`}>
                                {product.is_masked ? `#${item.product_id}` : `${product.product_name} (${product.unit})`}
                              </div>
                            )}
                          </td>

                          <td className={`whitespace-nowrap px-4 py-3 text-right tabular-nums font-semibold ${deltaColorClass}`}>
                            {isPositive ? `+${formatNumber(delta)}` : formatNumber(delta)}
                          </td>

                          <td className="whitespace-nowrap px-4 py-3">
                            <div className="inline-flex flex-wrap items-center gap-1.5">
                              <span
                                className={`inline-flex rounded-full px-3 py-1 text-xs font-semibold ${
                                  isVoided ? 'bg-slate-100 text-slate-400 line-through' : typeStyle
                                }`}
                              >
                                {typeLabel}
                              </span>
                              {isVoided && (
                                <span className="inline-flex rounded-full bg-slate-200/80 px-2 py-0.5 text-[11px] font-medium text-slate-500 no-underline">
                                  ยกเลิกแล้ว
                                </span>
                              )}
                            </div>
                          </td>

                          <td className={`px-4 py-3 ${isVoided ? 'text-slate-400 line-through' : 'text-slate-600'}`}>
                            {formatSource(item.source_type, item.source_id)}
                          </td>

                          <td className="px-4 py-3">
                            {item.note ? (
                              <span
                                className={
                                  item.is_masked
                                    ? `font-mono text-slate-400 ${isVoided ? 'line-through' : ''}`
                                    : isVoided
                                      ? 'text-slate-400 line-through'
                                      : 'text-slate-600'
                                }
                              >
                                {item.note}
                              </span>
                            ) : (
                              <span className="text-slate-400">-</span>
                            )}
                            {item.decrypt_failed && (
                              <span className="ml-2 rounded bg-rose-50 px-1.5 py-0.5 text-[11px] font-medium text-rose-600">
                                ถอดรหัสไม่สำเร็จ
                              </span>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              {movementsTotal > MOVEMENTS_LIMIT && (
                <div className="flex flex-col gap-2 border-t border-slate-100 px-4 py-3 text-xs text-slate-500 sm:flex-row sm:items-center sm:justify-between">
                  <span>
                    แสดง {movementsPageStart}–{movementsPageEnd} จาก {movementsTotal} รายการ
                  </span>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      disabled={movementsOffset === 0 || movementsLoading}
                      onClick={() => setMovementsOffset((prev) => Math.max(0, prev - MOVEMENTS_LIMIT))}
                      className="rounded-lg border border-slate-200 px-3 py-1.5 font-medium text-slate-600 hover:bg-slate-50 disabled:opacity-40"
                    >
                      ก่อนหน้า
                    </button>
                    <button
                      type="button"
                      disabled={movementsOffset + MOVEMENTS_LIMIT >= movementsTotal || movementsLoading}
                      onClick={() => setMovementsOffset((prev) => prev + MOVEMENTS_LIMIT)}
                      className="rounded-lg border border-slate-200 px-3 py-1.5 font-medium text-slate-600 hover:bg-slate-50 disabled:opacity-40"
                    >
                      ถัดไป
                    </button>
                  </div>
                </div>
              )}
            </>
          )}
        </section>
      )}
    </div>
  );
}

export default Stock;
