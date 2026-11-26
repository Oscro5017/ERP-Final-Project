// Number display used across the app, so a change of format happens in one place.

const EMPTY = '-';

const toNumber = (value) => {
  if (value === null || value === undefined || value === '') return null;
  const number = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(number) ? number : null;
};

/** Fixed decimals, e.g. prices and totals: 1,234.50 */
export function formatNumber(value, decimals = 2) {
  const number = toNumber(value);
  if (number === null) return value === null || value === undefined || value === '' ? EMPTY : String(value);
  return number.toLocaleString('th-TH', { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

/** Quantities and counts, up to 3 decimals without trailing zeros: 1,234.5 */
export function formatQuantity(value) {
  const number = toNumber(value);
  if (number === null) return value === null || value === undefined || value === '' ? EMPTY : String(value);
  return number.toLocaleString('th-TH', { maximumFractionDigits: 3 });
}

/** Money with the baht sign: 1,234.50 ฿ */
export function formatMoney(value) {
  const number = toNumber(value);
  if (number === null) return value === null || value === undefined || value === '' ? EMPTY : String(value);
  return `${formatNumber(number)} ฿`;
}
