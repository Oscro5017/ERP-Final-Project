import { Menu, LogOut } from 'lucide-react';
import { getRole } from '../lib/api';

function Navbar({ onMenuToggle, onLogout }) {
  const role = getRole();
  const roleLabel = role === 'developer' ? 'DEVELOPER' : role === 'owner' ? 'OWNER' : 'ผู้ใช้งาน';

  return (
    <header className="sticky top-0 z-20 flex items-center justify-between border-b border-slate-200 bg-white/90 px-4 py-4 backdrop-blur md:px-6">
      <div className="flex items-center">
        <button onClick={onMenuToggle} aria-label="ย่อหรือขยายเมนู" className="rounded-xl border border-slate-200 p-2 text-slate-600 md:hidden">
          <Menu size={18} />
        </button>
      </div>

      <div className="flex items-center gap-3">
        <span className="rounded-full border border-slate-200 px-3 py-2 text-xs font-semibold tracking-normal text-slate-600">{roleLabel}</span>
        <button onClick={onLogout} aria-label="ออกจากระบบ" className="rounded-xl border border-slate-200 p-2 text-slate-600 transition hover:bg-slate-100" title="ออกจากระบบ">
          <LogOut size={18} />
        </button>
      </div>
    </header>
  );
}

export default Navbar;
