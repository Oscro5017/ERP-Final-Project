const labels = { expired_lot: 'มีของหมดอายุ', negative_balance: 'ยอดคงเหลือติดลบ', unit_mismatch: 'หน่วยไม่ตรง ไม่ได้ตัดสต็อก' };

/** names: optional { productId: name } so the warning can name the item. */
export const formatStockWarning = (warning, names = {}) => {
  const [code, productId] = warning.split(':');
  const label = labels[code];
  return label ? `${label}${names[productId] ? ` (${names[productId]})` : ''}` : warning;
};
