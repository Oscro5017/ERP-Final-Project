import { useState } from 'react';
import { Outlet } from 'react-router-dom';
import Sidebar from '../components/Sidebar';
import Navbar from '../components/Navbar';

function DashboardLayout({ children, onLogout }) {
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <div className="min-h-screen bg-[#f5f7f3] text-slate-800">
      {mobileOpen && <button type="button" aria-label="ปิดเมนู" onClick={() => setMobileOpen(false)} className="fixed inset-0 z-30 bg-slate-950/45 backdrop-blur-[2px] md:hidden" />}
      <Sidebar
        collapsed={collapsed}
        mobileOpen={mobileOpen}
        onToggle={() => setCollapsed((prev) => !prev)}
        onNavigate={() => setMobileOpen(false)}
      />
      <div className={`min-h-screen transition-[margin] duration-300 ${collapsed ? 'md:ml-[76px]' : 'md:ml-64 xl:ml-72'}`}>
        <Navbar onMenuToggle={() => setMobileOpen((prev) => !prev)} onLogout={onLogout} />
        <main className="mx-auto w-full max-w-[1600px] p-4 sm:p-5 md:p-7 xl:p-9">
          {children || <Outlet />}
        </main>
      </div>
    </div>
  );
}

export default DashboardLayout;
