import { useId, useRef, useState } from 'react';
import { ChevronDown, Plus, X } from 'lucide-react';

/** Pick one option by typing part of its name or clicking. options: [{ value, label, hint }] */
function SearchSelect({ label, value, onChange, options, placeholder = 'เลือก', onCreate, createLabel = 'เพิ่ม' }) {
  const id = useId();
  const inputRef = useRef(null);
  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [active, setActive] = useState(0);
  const selected = options.find((option) => String(option.value) === String(value ?? ''));
  const words = query.trim().toLowerCase();
  const matches = options.filter((option) => `${option.label} ${option.hint || ''}`.toLowerCase().includes(words));
  const canCreate = onCreate && words && !options.some((option) => option.label.toLowerCase() === words);
  const rows = canCreate ? [...matches, { create: true }] : matches;

  const open = () => {
    if (isOpen) return;
    setQuery('');
    setActive(Math.max(0, options.indexOf(selected)));
    setIsOpen(true);
  };

  const choose = (row) => {
    setIsOpen(false);
    if (row.create) onCreate(query.trim());
    else onChange(String(row.value));
  };

  const onKeyDown = (event) => {
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      if (!isOpen) {
        open();
        return;
      }
      const step = event.key === 'ArrowDown' ? 1 : -1;
      setActive((current) => (rows.length ? (current + step + rows.length) % rows.length : 0));
    } else if (event.key === 'Enter' && isOpen) {
      event.preventDefault();
      if (rows[active]) choose(rows[active]);
    } else if (event.key === 'Escape') {
      setIsOpen(false);
    }
  };

  return (
    <div className="relative">
      <label htmlFor={id} className="mb-1 block text-xs font-medium text-slate-600">{label}</label>
      <div className="relative">
        <input
          id={id}
          ref={inputRef}
          role="combobox"
          aria-expanded={isOpen}
          aria-controls={`${id}-list`}
          aria-activedescendant={isOpen && rows.length ? `${id}-${active}` : undefined}
          autoComplete="off"
          value={isOpen ? query : selected?.label || ''}
          placeholder={selected?.label || placeholder}
          onFocus={open}
          onClick={open}
          onBlur={() => setIsOpen(false)}
          onChange={(event) => { setIsOpen(true); setQuery(event.target.value); setActive(0); }}
          onKeyDown={onKeyDown}
          className="w-full rounded-xl border border-slate-200 bg-white py-2 pl-3 pr-9 text-sm outline-none focus:border-farm-700"
        />
        {selected ? (
          <button type="button" aria-label={`ล้าง${label}`} onMouseDown={(event) => event.preventDefault()} onClick={() => { setIsOpen(false); onChange(''); }} className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-slate-400 hover:text-slate-700"><X size={14} /></button>
        ) : <ChevronDown size={15} className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-slate-400" />}
      </div>
      {isOpen && (
        <ul id={`${id}-list`} role="listbox" aria-label={label} className="absolute z-20 mt-1 max-h-52 w-full overflow-y-auto rounded-xl border border-slate-200 bg-white py-1 shadow-lg">
          {rows.map((row, index) => (
            <li
              key={row.create ? 'create' : row.value}
              id={`${id}-${index}`}
              role="option"
              aria-selected={row === selected}
              onMouseDown={(event) => { event.preventDefault(); choose(row); inputRef.current?.blur(); }}
              onMouseEnter={() => setActive(index)}
              className={`flex cursor-pointer items-center justify-between gap-3 px-3 py-2 text-sm ${index === active ? 'bg-farm-50' : ''}`}
            >
              {row.create ? <span className="inline-flex items-center gap-1 font-medium text-farm-700"><Plus size={14} />{createLabel} “{query.trim()}”</span> : (
                <><span className="min-w-0 break-words text-slate-800">{row.label}</span>{row.hint && <span className="shrink-0 text-xs text-slate-500">{row.hint}</span>}</>
              )}
            </li>
          ))}
          {rows.length === 0 && <li className="px-3 py-2 text-sm text-slate-500">ไม่พบรายการ</li>}
        </ul>
      )}
    </div>
  );
}

export default SearchSelect;
