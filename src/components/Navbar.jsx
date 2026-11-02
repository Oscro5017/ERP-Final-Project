import { Bell, Search, Menu, LogOut } from 'lucide-react';

function Navbar({ onMenuToggle, collapsed, onLogout }) {
  return (
    <header className="sticky top-0 z-20 flex items-center justify-between border-b border-slate-200 bg-white/90 px-4 py-4 backdrop-blur md:px-6">
      <div className="flex items-center gap-3">
        <button onClick={onMenuToggle} className="rounded-xl border border-slate-200 p-2 text-slate-600 md:hidden">
          <Menu size={18} />
        </button>
        <div className="hidden items-center gap-2 rounded-full border border-slate-200 bg-slate-50 px-3 py-2 md:flex">
          <Search size={16} className="text-slate-400" />
          <input className="w-56 bg-transparent text-sm outline-none" placeholder="ค้นหา" />
        </div>
      </div>

      <div className="flex items-center gap-3">
        <button className="relative rounded-full border border-slate-200 p-2 text-slate-600">
          <Bell size={18} />
          <span className="absolute right-1 top-1 h-2.5 w-2.5 rounded-full bg-red-500" />
        </button>
        <div className="flex items-center gap-3 rounded-full border border-slate-200 px-3 py-2">
          <div className="flex h-9 w-9 items-center justify-center rounded-full bg-farm-700 text-sm font-semibold text-white">ก</div>
          <div className="hidden text-left md:block">
            <p className="text-sm font-semibold text-slate-700">กรกช บุญมี</p>
            <p className="text-xs text-slate-500">ผู้จัดการฟาร์ม</p>
          </div>
        </div>
        <button onClick={onLogout} className="rounded-xl border border-slate-200 p-2 text-slate-600 transition hover:bg-slate-100" title="ออกจากระบบ">
          <LogOut size={18} />
        </button>
      </div>
    </header>
  );
}

export default Navbar;
