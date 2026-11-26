import { useEffect, useRef, useState } from 'react';
import { CalendarDays } from 'lucide-react';
import { formatThaiDateInput, parseThaiDateInput } from '../utils/dateUtils';

function ThaiDateInput({ value, onChange, className = '', label, required = false }) {
  const [draft, setDraft] = useState(formatThaiDateInput(value));
  const datePickerRef = useRef(null);
  const textInputRef = useRef(null);

  useEffect(() => {
    setDraft(formatThaiDateInput(value));
  }, [value]);

  const handleTextChange = (event) => {
    const nextValue = event.target.value;
    setDraft(nextValue);

    if (!nextValue.trim()) {
      event.target.setCustomValidity('');
      onChange('');
      return;
    }

    const parsedDate = parseThaiDateInput(nextValue);
    if (!parsedDate) {
      event.target.setCustomValidity('กรุณากรอกวันที่เป็น วัน/เดือน/ปี พ.ศ. เช่น 01/11/2569');
      return;
    }

    event.target.setCustomValidity('');
    onChange(parsedDate);
  };

  const handleDatePickerChange = (event) => {
    const nextValue = event.target.value;
    setDraft(formatThaiDateInput(nextValue));
    textInputRef.current?.setCustomValidity('');
    onChange(nextValue);
  };

  const openDatePicker = () => {
    const picker = datePickerRef.current;
    if (picker?.showPicker) picker.showPicker();
    else picker?.click();
  };

  return (
    <div className={`relative flex items-center ${className}`}>
      <input
        ref={textInputRef}
        type="text"
        value={draft}
        onChange={handleTextChange}
        required={required}
        inputMode="numeric"
        placeholder="วว/ดด/ปปปป"
        aria-label={label}
        className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 pr-10 font-normal"
      />
      <button
        type="button"
        onClick={openDatePicker}
        aria-label={label ? `เลือก${label}` : 'เลือกวันที่'}
        className="absolute right-2 rounded-lg p-1.5 text-slate-500 hover:bg-slate-100"
      >
        <CalendarDays size={16} />
      </button>
      <input
        ref={datePickerRef}
        type="date"
        value={value}
        onChange={handleDatePickerChange}
        tabIndex={-1}
        aria-hidden="true"
        className="pointer-events-none absolute h-0 w-0 opacity-0"
      />
    </div>
  );
}

export default ThaiDateInput;
