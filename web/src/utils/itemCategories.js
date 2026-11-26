export const CATEGORIES = ['vegetable', 'seed', 'fertilizer', 'chemical', 'blend', 'other'];

export const CATEGORY_LABELS = {
  vegetable: 'ผลผลิต',
  seed: 'เมล็ดพันธุ์',
  fertilizer: 'ปุ๋ย',
  chemical: 'สารเคมี',
  blend: 'วัสดุผสม',
  other: 'อื่น ๆ',
};

/** Readable name of a stock item; masked names are ciphertext, so show its type instead. */
export const itemName = (item) => (item.is_masked
  ? `${CATEGORY_LABELS[item.category] || 'รายการ'} (ปิดบัง · ลำดับ ${item.id})`
  : item.name);

export const partnerName = (partner, kind) => (partner.is_masked ? `${kind} (ปิดบัง · ลำดับ ${partner.id})` : partner.name);

export const cycleName = (cycle) => `โต๊ะ ${cycle.table.table_number} · ${cycle.crop_type.name} · ${cycle.cycle_code}`;
