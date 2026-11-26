const FAMILIES = [
  { kg: 1, 'กก.': 1, กิโลกรัม: 1, g: 0.001, กรัม: 0.001 },
  { l: 1, ลิตร: 1, ml: 0.001, 'มล.': 0.001, มิลลิลิตร: 0.001 },
];
const key = (unit) => (unit || '').trim().toLowerCase();
const familyOf = (unit) => FAMILIES.find((family) => key(unit) in family);

/** The item's own unit plus the other scale of the same kind. */
export function compatibleUnits(unit) {
  const family = familyOf(unit);
  if (!family) return [unit];
  const factor = family[key(unit)];
  const isThai = /[ก-๙]/.test(unit);
  const other = Object.keys(family).find((name) => family[name] !== factor && /[ก-๙]/.test(name) === isThai);
  return [unit, other];
}

/** Quantity in another unit, or null when the units do not convert. */
export function convert(quantity, from, to) {
  if (key(from) === key(to)) return quantity;
  const family = familyOf(from);
  if (!family || family !== familyOf(to)) return null;
  return Number(((quantity * family[key(from)]) / family[key(to)]).toFixed(3));
}
