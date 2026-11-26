import { createContext, useCallback, useContext, useMemo, useState } from 'react';
import Modal from './Modal';

const DialogContext = createContext(null);

/**
 * In-app replacements for window.confirm and window.alert.
 * confirm(message | { title, message, confirmLabel, danger }) resolves to true or false;
 * alert(message | { title, message }) resolves once the user closes it.
 */
export function DialogProvider({ children }) {
  const [dialog, setDialog] = useState(null);

  const open = useCallback((kind, options) => new Promise((resolve) => {
    const settings = typeof options === 'string' ? { message: options } : options;
    setDialog({ kind, resolve, ...settings });
  }), []);

  const close = (result) => {
    dialog.resolve(result);
    setDialog(null);
  };

  const value = useMemo(() => ({
    confirm: (options) => open('confirm', options),
    alert: (options) => open('alert', options),
  }), [open]);

  const isConfirm = dialog?.kind === 'confirm';
  const title = dialog?.title || (isConfirm ? 'ยืนยัน' : 'แจ้งเตือน');

  return (
    <DialogContext.Provider value={value}>
      {children}
      <Modal isOpen={Boolean(dialog)} title={title} onClose={() => close(isConfirm ? false : undefined)}>
        {dialog && (
          <div className="space-y-4 text-sm">
            <p className="whitespace-pre-line text-slate-700">{dialog.message}</p>
            <div className="flex justify-end gap-2">
              {isConfirm && (
                <button type="button" onClick={() => close(false)} className="rounded-xl border border-slate-200 px-4 py-2 font-medium text-slate-600 hover:bg-slate-50">
                  ยกเลิก
                </button>
              )}
              <button
                type="button"
                autoFocus
                onClick={() => close(isConfirm ? true : undefined)}
                className={`rounded-xl px-4 py-2 font-semibold text-white ${isConfirm && dialog.danger !== false ? 'bg-rose-600 hover:bg-rose-700' : 'bg-farm-700 hover:bg-farm-800'}`}
              >
                {isConfirm ? dialog.confirmLabel || 'ยืนยัน' : 'ตกลง'}
              </button>
            </div>
          </div>
        )}
      </Modal>
    </DialogContext.Provider>
  );
}

export const useDialog = () => useContext(DialogContext);
