function Toast({ message, visible }) {
  if (!visible) return null;

  return (
    <div className="fixed bottom-6 right-6 z-[60] rounded-xl bg-farm-800 px-4 py-3 text-sm font-medium text-white shadow-soft">
      {message}
    </div>
  );
}

export default Toast;
