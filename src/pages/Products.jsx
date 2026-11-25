import { useCallback, useEffect, useRef, useState } from 'react';
import { Search, Plus, Filter, Pencil, Trash2, Package, Scale } from 'lucide-react';
import { api, getRole } from '../lib/api';
import Modal from '../components/Modal';
import Toast from '../components/Toast';

const CATEGORIES = [
  'vegetable',
  'seed',
  'fertilizer',
  'chemical',
  'blend',
  'other',
];

const CATEGORY_LABELS = {
  vegetable: 'ผัก / ผลผลิต',
  seed: 'เมล็ดพันธุ์',
  fertilizer: 'ปุ๋ย',
  chemical: 'สารเคมี',
  blend: 'วัสดุผสม',
  other: 'อื่นๆ',
};

const PAGE_LIMIT = 50;

const emptyProductForm = {
  category: 'vegetable',
  name: '',
  unit: '',
  reorder_point: '',
  is_active: true,
};

const emptyAdjustForm = {
  counted_quantity: '',
  unit: '',
  note: '',
  occurred_at: '',
};

function formatNumber(value) {
  if (value === null || value === undefined || value === '') return '-';
  const num = Number(value);
  if (Number.isNaN(num)) return '-';
  return num.toLocaleString('th-TH', { maximumFractionDigits: 3 });
}

function getStockStatus(item) {
  if (item.is_negative) {
    return { label: 'ติดลบ', className: 'bg-red-100 text-red-700' };
  }
  if (item.is_low) {
    return { label: 'ใกล้หมด', className: 'bg-rose-100 text-rose-700' };
  }
  return { label: 'ปกติ', className: 'bg-green-100 text-green-700' };
}

function Products() {
  const role = getRole();
  const isOwner = role === 'owner';

  const [products, setProducts] = useState([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [search, setSearch] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState('');

  const [isProductModalOpen, setIsProductModalOpen] = useState(false);
  const [editingProduct, setEditingProduct] = useState(null);
  const [productForm, setProductForm] = useState(emptyProductForm);
  const [productFormError, setProductFormError] = useState('');
  const [isSavingProduct, setIsSavingProduct] = useState(false);

  const [adjustingProduct, setAdjustingProduct] = useState(null);
  const [adjustForm, setAdjustForm] = useState(emptyAdjustForm);
  const [adjustFormError, setAdjustFormError] = useState('');
  const [isSavingAdjust, setIsSavingAdjust] = useState(false);

  const [toastMessage, setToastMessage] = useState('');
  const toastTimerRef = useRef(null);

  const showToast = useCallback((message) => {
    setToastMessage(message);
    if (toastTimerRef.current) {
      window.clearTimeout(toastTimerRef.current);
    }
    toastTimerRef.current = window.setTimeout(() => {
      setToastMessage('');
    }, 2400);
  }, []);

  useEffect(() => {
    return () => {
      if (toastTimerRef.current) {
        window.clearTimeout(toastTimerRef.current);
      }
    };
  }, []);

  const loadProducts = useCallback(async (currentSearch = search, currentCategory = categoryFilter, currentOffset = offset) => {
    setIsLoading(true);
    setErrorMessage('');
    try {
      const params = new URLSearchParams({
        limit: String(PAGE_LIMIT),
        offset: String(currentOffset),
      });
      if (currentCategory) {
        params.set('category', currentCategory);
      }
      if (currentSearch.trim()) {
        params.set('q', currentSearch.trim());
      }
      const data = await api(`/products?${params.toString()}`);
      setProducts(Array.isArray(data?.items) ? data.items : []);
      setTotal(typeof data?.total === 'number' ? data.total : 0);
    } catch (error) {
      setErrorMessage(error.message || 'ไม่สามารถโหลดข้อมูลสินค้าได้');
    } finally {
      setIsLoading(false);
    }
  }, [categoryFilter, offset, search]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      loadProducts(search, categoryFilter, offset);
    }, 250);
    return () => window.clearTimeout(timer);
  }, [search, categoryFilter, offset, loadProducts]);

  const handleSearchChange = (event) => {
    setSearch(event.target.value);
    setOffset(0);
  };

  const handleCategoryChange = (event) => {
    setCategoryFilter(event.target.value);
    setOffset(0);
  };

  const openCreateModal = () => {
    setEditingProduct(null);
    setProductForm(emptyProductForm);
    setProductFormError('');
    setIsProductModalOpen(true);
  };

  const openEditModal = (product) => {
    setEditingProduct(product);
    setProductForm({
      category: product.category || 'other',
      name: product.is_masked ? '' : (product.name || ''),
      unit: product.unit || '',
      reorder_point: product.reorder_point !== null && product.reorder_point !== undefined ? String(product.reorder_point) : '',
      is_active: product.is_active ?? true,
    });
    setProductFormError('');
    setIsProductModalOpen(true);
  };

  const closeProductModal = () => {
    setIsProductModalOpen(false);
    setEditingProduct(null);
    setProductFormError('');
  };

  const handleProductSubmit = async (event) => {
    event.preventDefault();
    setProductFormError('');

    const trimmedName = productForm.name.trim();
    const trimmedUnit = productForm.unit.trim();
    const needsName = !editingProduct || !editingProduct.is_masked;

    if (needsName && !trimmedName) {
      setProductFormError('กรุณาระบุชื่อสินค้า');
      return;
    }
    if (!trimmedUnit) {
      setProductFormError('กรุณาระบุหน่วยสินค้า');
      return;
    }

    let reorderPointValue = null;
    if (productForm.reorder_point !== '') {
      const parsed = Number(productForm.reorder_point);
      if (Number.isNaN(parsed) || parsed < 0) {
        setProductFormError('จุดสั่งซื้อต้องเป็นตัวเลขตั้งแต่ 0 ขึ้นไป');
        return;
      }
      reorderPointValue = parsed;
    }

    setIsSavingProduct(true);
    try {
      if (editingProduct) {
        const payload = {
          category: productForm.category,
          unit: trimmedUnit,
          reorder_point: reorderPointValue,
          is_active: Boolean(productForm.is_active),
        };
        if (!editingProduct.is_masked) {
          payload.name = trimmedName;
        }
        await api(`/products/${editingProduct.id}`, {
          method: 'PATCH',
          body: JSON.stringify(payload),
        });
        showToast('บันทึกการแก้ไขสินค้าแล้ว');
      } else {
        const payload = {
          category: productForm.category,
          name: trimmedName,
          unit: trimmedUnit,
          reorder_point: reorderPointValue,
          is_active: Boolean(productForm.is_active),
        };
        await api('/products', {
          method: 'POST',
          body: JSON.stringify(payload),
        });
        showToast('เพิ่มสินค้าเรียบร้อยแล้ว');
      }
      closeProductModal();
      await loadProducts(search, categoryFilter, offset);
    } catch (error) {
      setProductFormError(error.message || 'ไม่สามารถบันทึกข้อมูลสินค้าได้');
    } finally {
      setIsSavingProduct(false);
    }
  };

  const handleDeleteProduct = async (product) => {
    const displayName = product.is_masked ? `#${product.id} (ข้อมูลเข้ารหัส)` : product.name;
    if (!window.confirm(`ต้องการลบสินค้า "${displayName}" ใช่หรือไม่?`)) {
      return;
    }
    try {
      await api(`/products/${product.id}`, { method: 'DELETE' });
      showToast('ลบสินค้าแล้ว');
      const nextOffset = products.length === 1 && offset > 0 ? Math.max(0, offset - PAGE_LIMIT) : offset;
      if (nextOffset !== offset) {
        setOffset(nextOffset);
      } else {
        await loadProducts(search, categoryFilter, offset);
      }
    } catch (error) {
      showToast(error.message || 'ไม่สามารถลบสินค้าได้');
    }
  };

  const openAdjustModal = (product) => {
    setAdjustingProduct(product);
    setAdjustForm({
      counted_quantity: product.on_hand !== null && product.on_hand !== undefined ? String(Math.max(0, product.on_hand)) : '0',
      unit: product.unit || '',
      note: '',
      occurred_at: '',
    });
    setAdjustFormError('');
  };

  const closeAdjustModal = () => {
    setAdjustingProduct(null);
    setAdjustFormError('');
  };

  const handleAdjustSubmit = async (event) => {
    event.preventDefault();
    if (!adjustingProduct) return;
    setAdjustFormError('');

    const counted = Number(adjustForm.counted_quantity);
    if (adjustForm.counted_quantity === '' || Number.isNaN(counted) || counted < 0) {
      setAdjustFormError('จำนวนที่นับได้ต้องเป็นตัวเลขตั้งแต่ 0 ขึ้นไป');
      return;
    }

    const payload = {
      counted_quantity: counted,
    };
    if (adjustForm.unit.trim()) {
      payload.unit = adjustForm.unit.trim();
    }
    if (adjustForm.note.trim()) {
      payload.note = adjustForm.note.trim();
    }
    if (adjustForm.occurred_at) {
      payload.occurred_at = new Date(adjustForm.occurred_at).toISOString();
    }

    setIsSavingAdjust(true);
    try {
      await api(`/products/${adjustingProduct.id}/adjustments`, {
        method: 'POST',
        body: JSON.stringify(payload),
      });
      showToast('ปรับยอดสต็อกเรียบร้อยแล้ว');
      closeAdjustModal();
      await loadProducts(search, categoryFilter, offset);
    } catch (error) {
      setAdjustFormError(error.message || 'ไม่สามารถปรับยอดสต็อกได้');
    } finally {
      setIsSavingAdjust(false);
    }
  };

  const parsedCounted = Number(adjustForm.counted_quantity);
  const adjustDiff =
    adjustingProduct &&
    adjustForm.counted_quantity !== '' &&
    !Number.isNaN(parsedCounted) &&
    parsedCounted >= 0
      ? Number((parsedCounted - Number(adjustingProduct.on_hand || 0)).toFixed(3))
      : null;

  const canGoPrev = offset > 0;
  const canGoNext = offset + PAGE_LIMIT < total;

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex items-start gap-3">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-farm-50 text-farm-700 border border-slate-200 shadow-soft">
            <Package size={22} />
          </div>
          <div>
            <h1 className="text-2xl font-semibold text-slate-800">สินค้า</h1>
            <p className="text-sm text-slate-500">จัดการสินค้าทั้งวัตถุดิบและผลผลิต</p>
          </div>
        </div>
        <button
          type="button"
          onClick={openCreateModal}
          className="inline-flex items-center justify-center gap-2 rounded-xl bg-farm-700 px-4 py-2.5 text-sm font-semibold text-white shadow-soft transition hover:bg-farm-800"
        >
          <Plus size={16} />
          เพิ่มสินค้า
        </button>
      </div>

      <div className="flex flex-col gap-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-soft md:flex-row md:items-center md:justify-between">
        <div className="flex flex-1 items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 focus-within:border-farm-700">
          <Search size={16} className="shrink-0 text-slate-400" />
          <input
            type="text"
            value={search}
            onChange={handleSearchChange}
            placeholder="ค้นหาชื่อสินค้า"
            aria-label="ค้นหาชื่อสินค้า"
            className="w-full bg-transparent text-sm text-slate-700 outline-none placeholder:text-slate-400"
          />
        </div>
        <div className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2">
          <Filter size={16} className="shrink-0 text-slate-500" />
          <select
            value={categoryFilter}
            onChange={handleCategoryChange}
            aria-label="กรองตามประเภทสินค้า"
            className="bg-transparent text-sm text-slate-700 outline-none"
          >
            <option value="">ทุกประเภท</option>
            {CATEGORIES.map((cat) => (
              <option key={cat} value={cat}>
                {CATEGORY_LABELS[cat]}
              </option>
            ))}
          </select>
        </div>
      </div>

      {errorMessage && (
        <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
          {errorMessage}
        </div>
      )}

      <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-soft">
        <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3 text-sm text-slate-500">
          <span>ทั้งหมด {total.toLocaleString('th-TH')} รายการ</span>
          {!isOwner && (
            <span className="text-xs text-slate-400">
              ชื่อสินค้าถูกเข้ารหัสตามสิทธิ์ผู้ใช้งาน
            </span>
          )}
        </div>

        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead className="bg-slate-50 text-slate-600">
              <tr>
                <th className="px-4 py-3 font-semibold">ชื่อสินค้า</th>
                <th className="px-4 py-3 font-semibold">ประเภท</th>
                <th className="px-4 py-3 font-semibold">หน่วย</th>
                <th className="px-4 py-3 font-semibold text-right">คงเหลือ</th>
                <th className="px-4 py-3 font-semibold text-right">จุดสั่งซื้อ</th>
                <th className="px-4 py-3 font-semibold">สถานะ</th>
                <th className="px-4 py-3 font-semibold text-right">จัดการ</th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                <tr>
                  <td colSpan="7" className="px-4 py-8 text-center text-slate-500">
                    กำลังโหลดข้อมูลสินค้า...
                  </td>
                </tr>
              ) : products.length === 0 ? (
                <tr>
                  <td colSpan="7" className="px-4 py-10 text-center text-slate-500">
                    ไม่พบรายการสินค้า
                  </td>
                </tr>
              ) : (
                products.map((item) => {
                  const status = getStockStatus(item);
                  return (
                    <tr key={item.id} className="border-t border-slate-100 hover:bg-slate-50/70">
                      <td className="px-4 py-3">
                        <div className="flex flex-wrap items-center gap-2">
                          <span
                            className={
                              item.is_masked
                                ? 'font-mono text-slate-400 break-all'
                                : 'font-medium text-slate-800'
                            }
                            title={item.is_masked ? item.name : undefined}
                          >
                            {item.name}
                          </span>
                          {item.decrypt_failed && (
                            <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-700">
                              ถอดรหัสไม่สำเร็จ
                            </span>
                          )}
                          {item.is_active === false && (
                            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-500">
                              ปิดใช้งาน
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="px-4 py-3 text-slate-700">
                        {CATEGORY_LABELS[item.category] || item.category}
                      </td>
                      <td className="px-4 py-3 text-slate-700">{item.unit}</td>
                      <td className="px-4 py-3 text-right font-medium text-slate-800">
                        {formatNumber(item.on_hand)}
                      </td>
                      <td className="px-4 py-3 text-right text-slate-600">
                        {formatNumber(item.reorder_point)}
                      </td>
                      <td className="px-4 py-3">
                        <span className={`inline-flex rounded-full px-3 py-1 text-xs font-semibold ${status.className}`}>
                          {status.label}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center justify-end gap-1">
                          <button
                            type="button"
                            onClick={() => openAdjustModal(item)}
                            className="inline-flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-xs font-medium text-farm-700 transition hover:bg-farm-50"
                            title="ปรับยอดสต็อก"
                            aria-label="ปรับยอดสต็อก"
                          >
                            <Scale size={15} />
                            <span>ปรับสต็อก</span>
                          </button>
                          <button
                            type="button"
                            onClick={() => openEditModal(item)}
                            className="rounded-lg p-2 text-slate-500 transition hover:bg-slate-100 hover:text-slate-700"
                            title="แก้ไขสินค้า"
                            aria-label="แก้ไขสินค้า"
                          >
                            <Pencil size={15} />
                          </button>
                          <button
                            type="button"
                            onClick={() => handleDeleteProduct(item)}
                            className="rounded-lg p-2 text-rose-500 transition hover:bg-rose-50"
                            title="ลบสินค้า"
                            aria-label="ลบสินค้า"
                          >
                            <Trash2 size={15} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        {(canGoPrev || canGoNext) && (
          <div className="flex items-center justify-between border-t border-slate-200 px-4 py-3 text-sm text-slate-600">
            <span>
              แสดง {total === 0 ? 0 : offset + 1} - {Math.min(offset + PAGE_LIMIT, total)} จาก {total}
            </span>
            <div className="flex items-center gap-2">
              <button
                type="button"
                disabled={!canGoPrev}
                onClick={() => setOffset((prev) => Math.max(0, prev - PAGE_LIMIT))}
                className="rounded-xl border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-700 transition hover:bg-slate-50 disabled:opacity-40"
              >
                ก่อนหน้า
              </button>
              <button
                type="button"
                disabled={!canGoNext}
                onClick={() => setOffset((prev) => prev + PAGE_LIMIT)}
                className="rounded-xl border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-700 transition hover:bg-slate-50 disabled:opacity-40"
              >
                ถัดไป
              </button>
            </div>
          </div>
        )}
      </div>

      <Modal
        isOpen={isProductModalOpen}
        title={editingProduct ? 'แก้ไขสินค้า' : 'เพิ่มสินค้า'}
        onClose={closeProductModal}
      >
        <form onSubmit={handleProductSubmit} className="space-y-4">
          {productFormError && (
            <div className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
              {productFormError}
            </div>
          )}

          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">ประเภทสินค้า</label>
            <select
              value={productForm.category}
              onChange={(event) => setProductForm((prev) => ({ ...prev, category: event.target.value }))}
              className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 outline-none focus:border-farm-700"
            >
              {CATEGORIES.map((cat) => (
                <option key={cat} value={cat}>
                  {CATEGORY_LABELS[cat]}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">ชื่อสินค้า</label>
            {editingProduct?.is_masked ? (
              <div className="space-y-1">
                <input
                  type="text"
                  value={editingProduct.name}
                  disabled
                  className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 font-mono text-sm text-slate-400"
                />
                <p className="text-xs text-slate-400">
                  ข้อมูลชื่อสินค้าถูกเข้ารหัส จึงไม่สามารถแก้ไขชื่อในสิทธิ์นี้ได้
                </p>
              </div>
            ) : (
              <input
                type="text"
                required
                maxLength={160}
                value={productForm.name}
                onChange={(event) => setProductForm((prev) => ({ ...prev, name: event.target.value }))}
                placeholder="เช่น ผักสลัดกรีนโอ๊ค หรือ ปุ๋ยอินทรีย์"
                className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm text-slate-800 outline-none focus:border-farm-700"
              />
            )}
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <label className="mb-1 block text-sm font-medium text-slate-700">หน่วยนับ</label>
              <input
                type="text"
                required
                maxLength={80}
                value={productForm.unit}
                onChange={(event) => setProductForm((prev) => ({ ...prev, unit: event.target.value }))}
                placeholder="เช่น กก., ถุง, ขวด"
                className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm text-slate-800 outline-none focus:border-farm-700"
              />
            </div>

            <div>
              <label className="mb-1 block text-sm font-medium text-slate-700">จุดสั่งซื้อ</label>
              <input
                type="number"
                min="0"
                step="any"
                value={productForm.reorder_point}
                onChange={(event) => setProductForm((prev) => ({ ...prev, reorder_point: event.target.value }))}
                placeholder="ไม่ระบุ"
                className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm text-slate-800 outline-none focus:border-farm-700"
              />
            </div>
          </div>

          <label className="flex items-center gap-2 text-sm text-slate-700">
            <input
              type="checkbox"
              checked={productForm.is_active}
              onChange={(event) => setProductForm((prev) => ({ ...prev, is_active: event.target.checked }))}
              className="h-4 w-4 rounded border-slate-300 text-farm-700"
            />
            เปิดใช้งานสินค้า
          </label>

          <div className="flex items-center justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={closeProductModal}
              className="rounded-xl border border-slate-200 px-4 py-2 text-sm font-medium text-slate-600 transition hover:bg-slate-50"
            >
              ยกเลิก
            </button>
            <button
              type="submit"
              disabled={isSavingProduct}
              className="rounded-xl bg-farm-700 px-4 py-2 text-sm font-semibold text-white shadow-soft transition hover:bg-farm-800 disabled:opacity-60"
            >
              {isSavingProduct ? 'กำลังบันทึก...' : 'บันทึก'}
            </button>
          </div>
        </form>
      </Modal>

      <Modal
        isOpen={Boolean(adjustingProduct)}
        title="ปรับยอดสต็อก"
        onClose={closeAdjustModal}
      >
        {adjustingProduct && (
          <form onSubmit={handleAdjustSubmit} className="space-y-4">
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-3 text-sm">
              <div className="flex items-center justify-between gap-2">
                <span className="text-slate-500">สินค้า</span>
                <span
                  className={
                    adjustingProduct.is_masked
                      ? 'font-mono text-slate-400 break-all'
                      : 'font-semibold text-slate-800'
                  }
                >
                  {adjustingProduct.name}
                </span>
              </div>
              <div className="mt-1 flex items-center justify-between gap-2">
                <span className="text-slate-500">คงเหลือในระบบ</span>
                <span className="font-semibold text-slate-800">
                  {formatNumber(adjustingProduct.on_hand)} {adjustingProduct.unit}
                </span>
              </div>
            </div>

            {adjustFormError && (
              <div className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
                {adjustFormError}
              </div>
            )}

            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <label className="mb-1 block text-sm font-medium text-slate-700">จำนวนที่นับได้จริง</label>
                <input
                  type="number"
                  min="0"
                  step="any"
                  required
                  value={adjustForm.counted_quantity}
                  onChange={(event) => setAdjustForm((prev) => ({ ...prev, counted_quantity: event.target.value }))}
                  className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm text-slate-800 outline-none focus:border-farm-700"
                />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-slate-700">หน่วย</label>
                <input
                  type="text"
                  maxLength={80}
                  value={adjustForm.unit}
                  onChange={(event) => setAdjustForm((prev) => ({ ...prev, unit: event.target.value }))}
                  placeholder={adjustingProduct.unit}
                  className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm text-slate-800 outline-none focus:border-farm-700"
                />
              </div>
            </div>

            {adjustDiff !== null && (
              <p className="text-xs text-slate-500">
                ผลต่างจากยอดเดิม:{' '}
                <span className={adjustDiff < 0 ? 'font-semibold text-rose-600' : 'font-semibold text-farm-700'}>
                  {adjustDiff > 0 ? `+${formatNumber(adjustDiff)}` : formatNumber(adjustDiff)} {adjustingProduct.unit}
                </span>
              </p>
            )}

            <div>
              <label className="mb-1 block text-sm font-medium text-slate-700">วันเวลาที่ตรวจนับ (ไม่บังคับ)</label>
              <input
                type="datetime-local"
                value={adjustForm.occurred_at}
                onChange={(event) => setAdjustForm((prev) => ({ ...prev, occurred_at: event.target.value }))}
                className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm text-slate-800 outline-none focus:border-farm-700"
              />
            </div>

            <div>
              <label className="mb-1 block text-sm font-medium text-slate-700">หมายเหตุ (ไม่บังคับ)</label>
              <textarea
                rows={2}
                maxLength={500}
                value={adjustForm.note}
                onChange={(event) => setAdjustForm((prev) => ({ ...prev, note: event.target.value }))}
                placeholder="ระบุเหตุผลการปรับยอดสต็อก"
                className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm text-slate-800 outline-none focus:border-farm-700"
              />
            </div>

            <div className="flex items-center justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={closeAdjustModal}
                className="rounded-xl border border-slate-200 px-4 py-2 text-sm font-medium text-slate-600 transition hover:bg-slate-50"
              >
                ยกเลิก
              </button>
              <button
                type="submit"
                disabled={isSavingAdjust}
                className="inline-flex items-center gap-1.5 rounded-xl bg-farm-700 px-4 py-2 text-sm font-semibold text-white shadow-soft transition hover:bg-farm-800 disabled:opacity-60"
              >
                <Scale size={15} />
                {isSavingAdjust ? 'กำลังบันทึก...' : 'ยืนยันปรับยอด'}
              </button>
            </div>
          </form>
        )}
      </Modal>

      <Toast message={toastMessage} visible={Boolean(toastMessage)} />
    </div>
  );
}

export default Products;
