import { useEffect, useId, useState } from 'react';
import { api } from '../lib/api';

function AutocompleteInput({
  value,
  onChange,
  suggestionsUrl = '/input-catalog/suggestions',
  placeholder = '',
  onSuggestionSelect,
  label,
  className = '',
}) {
  const [suggestions, setSuggestions] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [suggestionsMasked, setSuggestionsMasked] = useState(false);
  const uniqueId = useId();
  const datalistId = `datalist-${uniqueId}`;

  useEffect(() => {
    const query = (value || '').trim();
    if (!query) {
      setSuggestions([]);
      setSuggestionsMasked(false);
      return undefined;
    }

    const timer = setTimeout(async () => {
      try {
        setIsLoading(true);
        const data = await api(`${suggestionsUrl}?q=${encodeURIComponent(query)}&limit=10`);
        setSuggestions(Array.isArray(data) ? data : data?.items || []);
        setSuggestionsMasked(Boolean(data?.is_masked));
      } catch (_error) {
        setSuggestions([]);
        setSuggestionsMasked(false);
      } finally {
        setIsLoading(false);
      }
    }, 300);

    return () => clearTimeout(timer);
  }, [value, suggestionsUrl]);

  return (
    <div className="w-full">
      {label && <label className="mb-1 block text-xs font-medium text-slate-600">{label}</label>}
      <input
        type="text"
        value={value}
        onChange={(event) => {
          onChange(event.target.value);
          if (onSuggestionSelect) {
            const selected = suggestions.find((item) => item.item_name === event.target.value);
            if (selected) {
              onSuggestionSelect(selected);
            }
          }
        }}
        onBlur={(event) => {
          const selected = suggestions.find((item) => item.item_name === event.target.value);
          if (selected && onSuggestionSelect) {
            onSuggestionSelect(selected);
          }
        }}
        list={datalistId}
        placeholder={placeholder}
        className={`w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-700 outline-none transition focus:border-farm-500 focus:ring-2 focus:ring-farm-100 ${className}`}
      />
      <datalist id={datalistId}>
        {suggestions.map((suggestion) => (
          <option key={suggestion.id} value={suggestion.item_name} />
        ))}
      </datalist>
      {isLoading && <div className="mt-1 text-[10px] text-slate-400">กำลังค้นหา…</div>}
      {suggestionsMasked && <div className="mt-1 text-[10px] text-slate-400">คำแนะนำถูกปิดบัง</div>}
    </div>
  );
}

export default AutocompleteInput;
