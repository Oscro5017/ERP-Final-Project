/**
 * Calculates the next Tuesday starting from a given date.
 * If today is Tuesday, it returns the next Tuesday (+7 days)
 * since farm planting schedules start on the next upcoming Tuesday.
 */
export function getNextTuesday(fromDate = new Date()) {
  const d = new Date(fromDate);
  const day = d.getDay(); // 0 is Sunday, 2 is Tuesday
  const daysUntilTuesday = (2 - day + 7) % 7 || 7;
  d.setDate(d.getDate() + daysUntilTuesday);
  return getLocalDateString(d);
}

export function getLocalDateString(value = new Date()) {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, '0');
  const day = String(value.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function getThaiDateParts(date) {
  const parts = new Intl.DateTimeFormat('th-TH-u-ca-buddhist', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  }).formatToParts(date);
  return Object.fromEntries(parts.map(({ type, value }) => [type, value]));
}

/**
 * Formats a date string (YYYY-MM-DD) as DD/MM/YYYY using the Buddhist calendar.
 */
export function formatThaiDate(value) {
  if (!value || !/^\d{4}-\d{2}-\d{2}/.test(value)) return value || '-';
  const cleanDate = value.slice(0, 10);
  const { day, month, year } = getThaiDateParts(new Date(`${cleanDate}T00:00:00`));
  return `${day}/${month}/${year}`;
}

export function formatThaiDateTime(value) {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const { day, month, year } = getThaiDateParts(date);
  const time = new Intl.DateTimeFormat('th-TH', {
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  }).format(date);
  return `${day}/${month}/${year} ${time}`;
}

export function formatThaiDateInput(value) {
  if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return '';
  const [year, month, day] = value.split('-');
  return `${day}/${month}/${Number(year) + 543}`;
}

export function parseThaiDateInput(value) {
  const match = /^(\d{1,2})\/(\d{1,2})\/(\d{4})$/.exec(value.trim());
  if (!match) return null;

  const day = Number(match[1]);
  const month = Number(match[2]);
  const year = Number(match[3]) - 543;
  const parsed = new Date(year, month - 1, day);
  if (
    parsed.getFullYear() !== year ||
    parsed.getMonth() !== month - 1 ||
    parsed.getDate() !== day
  ) return null;

  return `${String(year).padStart(4, '0')}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
}

/**
 * Formats a date string (YYYY-MM-DD) as a Thai weekday followed by DD/MM.
 */
export function formatThaiWeekdayDate(value) {
  if (!value || !/^\d{4}-\d{2}-\d{2}/.test(value)) return value || '-';
  const cleanDate = value.slice(0, 10);
  const d = new Date(`${cleanDate}T00:00:00`);
  const weekday = new Intl.DateTimeFormat('th-TH', { weekday: 'short' }).format(d);
  const { day, month } = getThaiDateParts(d);
  return `${weekday} ${day}/${month}`;
}

/**
 * Returns whether a given YYYY-MM-DD date is today, tomorrow, or in the past
 */
export function getRelativeDayLabel(value) {
  if (!value) return '';
  const todayStr = new Date().toISOString().slice(0, 10);
  const target = value.slice(0, 10);
  if (target === todayStr) return 'วันนี้';

  const todayDate = new Date(`${todayStr}T00:00:00`);
  const targetDate = new Date(`${target}T00:00:00`);
  const diffDays = Math.round((targetDate - todayDate) / (1000 * 60 * 60 * 24));

  if (diffDays === 1) return 'พรุ่งนี้';
  if (diffDays === -1) return 'เมื่อวาน';
  if (diffDays < 0) return `เกินกำหนด ${Math.abs(diffDays)} วัน`;
  return `อีก ${diffDays} วัน`;
}
