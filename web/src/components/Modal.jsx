function Modal({ isOpen, title, onClose, children, wide = false }) {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 px-4">
      <div role="dialog" aria-modal="true" aria-label={title} className={`w-full ${wide ? 'max-w-3xl' : 'max-w-lg'} rounded-2xl border border-slate-200 bg-white p-4 shadow-2xl sm:p-6`}>
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-lg font-semibold text-slate-800">{title}</h3>
          <button type="button" onClick={onClose} className="text-sm text-slate-500">ปิด</button>
        </div>
        {children}
      </div>
    </div>
  );
}

export default Modal;
