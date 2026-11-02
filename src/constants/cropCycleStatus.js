export const cropCycleStatuses = [
  { value: 'nursery', label: 'อนุบาล' },
  { value: 'bushed', label: 'สร้างพุ่ม' },
  { value: 'ready_to_harvest', label: 'พร้อมเก็บเกี่ยว' },
  { value: 'harvested', label: 'เก็บเกี่ยวแล้ว' },
  { value: 'empty', label: 'ว่าง' },
];

export const cropCycleStatusLabels = Object.fromEntries(
  cropCycleStatuses.map(({ value, label }) => [value, label]),
);