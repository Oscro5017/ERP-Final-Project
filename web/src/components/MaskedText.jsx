/** Shows a value, or a short grey token when it is ciphertext the current user may not read. */
function MaskedText({ value, isMasked, fallback = '-', className = '', strikethrough = false }) {
  if (value === null || value === undefined || value === '') {
    return <span className={className}>{fallback}</span>;
  }
  const text = String(value);
  if (!isMasked) {
    return (
      <span className={`${strikethrough ? 'line-through' : ''} ${className}`}>
        {text}
      </span>
    );
  }
  const shortened = text.length > 20 ? `${text.slice(0, 20)}…` : text;
  return (
    <span
      title={text}
      className={`inline-flex max-w-56 items-center truncate rounded-md bg-slate-100 px-2 py-0.5 font-mono text-xs text-slate-400 select-none ${strikethrough ? 'line-through' : ''} ${className}`}
    >
      {shortened}
    </span>
  );
}

export default MaskedText;
