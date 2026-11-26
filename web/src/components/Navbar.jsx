import { LogOut, Menu, Sprout } from 'lucide-react';
import { getRole } from '../lib/api';

function Navbar({ onMenuToggle, onLogout }) {
  const role = getRole();
  const roleLabel = role === 'developer' ? 'DEVELOPER' : role === 'owner' ? 'OWNER' : 'ผู้ใช้งาน';

  return (
    <header className="sticky top-0 z-20 flex h-[72px] items-center justify-between border-b border-[#e4e9e1] bg-white/95 px-4 backdrop-blur-md sm:px-5 md:px-7">
      <div className="flex min-w-0 items-center gap-3">
        <button onClick={onMenuToggle} aria-label="เปิดเมนูนำทาง" className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-slate-200 bg-white text-slate-600 transition hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-farm-600 md:hidden">
          <Menu size={19} aria-hidden="true" />
        </button>
        <div className="hidden h-9 w-9 items-center justify-center rounded-xl bg-farm-50 text-farm-700 sm:flex md:hidden">
          <Sprout size={19} aria-hidden="true" />
        </div>
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-slate-800">Organic Farm</p>
          <p className="hidden text-xs text-slate-500 sm:block">ศูนย์จัดการฟาร์ม</p>
        </div>
      </div>

      <div className="flex items-center gap-3">
        <span className="rounded-full border border-farm-100 bg-farm-50 px-3 py-1.5 text-[11px] font-semibold tracking-wide text-farm-800 sm:text-xs">{roleLabel}</span>
        <span className="hidden h-7 w-px bg-slate-200 sm:block" aria-hidden="true" />
        <button onClick={onLogout} aria-label="ออกจากระบบ" className="inline-flex h-11 w-11 items-center justify-center rounded-xl border border-slate-200 bg-white text-slate-600 transition hover:border-rose-200 hover:bg-rose-50 hover:text-rose-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-farm-600" title="ออกจากระบบ">
          <LogOut size={18} aria-hidden="true" />
        </button>
      </div>
    </header>
  );
}

export default Navbar;
