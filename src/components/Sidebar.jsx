import { NavLink } from 'react-router-dom';
import { LayoutDashboard, CloudSun, Sprout, ClipboardList, Leaf, Warehouse, ShoppingCart, Wallet, BarChart3, Users, Settings, ChevronLeft, ChevronRight, ArrowUpRight } from 'lucide-react';
import { sidebarItems } from '../data/mockData';

const icons = {
  LayoutDashboard,
  CloudSun,
  Sprout,
  ClipboardList,
  Leaf,
  Warehouse,
  ShoppingCart,
  Wallet,
  BarChart3,
  Users,
  Settings,
};

function Sidebar({ collapsed, onToggle }) {
  return (
    <aside className={`fixed left-0 top-0 z-30 h-screen border-r border-farm-700/20 bg-farm-900 text-white transition-all duration-300 ${collapsed ? 'w-20' : 'w-72'}`}>
      <div className="flex h-full flex-col">
        <div className="flex items-center justify-between px-4 py-5">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-farm-700/80">
              <Sprout size={20} />
            </div>
            {!collapsed && <div>
              <p className="text-sm font-semibold">Organic Farm</p>
              <p className="text-xs text-farm-300">Management System</p>
            </div>}
          </div>
          <button onClick={onToggle} className="rounded-full p-2 text-farm-300 transition hover:bg-farm-800">
            {collapsed ? <ChevronRight size={18} /> : <ChevronLeft size={18} />}
          </button>
        </div>

        <nav className="mt-4 flex-1 px-3">
          {sidebarItems.map((item) => {
            const Icon = icons[item.icon];
            return (
              <NavLink
                key={item.path}
                to={item.path}
                className={({ isActive }) => `mb-1 flex items-center gap-3 rounded-xl px-3 py-3 text-sm font-medium transition ${isActive ? 'bg-farm-700 text-white shadow-soft' : 'text-farm-100 hover:bg-farm-800'}`}
              >
                <Icon size={18} />
                {!collapsed && <span>{item.name}</span>}
              </NavLink>
            );
          })}
        </nav>

        <div className="border-t border-farm-700/30 p-4">
          <div className="flex items-center gap-3 rounded-xl bg-farm-800/70 p-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-farm-700 text-sm font-semibold">ก</div>
            {!collapsed && <div className="flex-1">
              <p className="text-sm font-semibold">กรกช</p>
              <p className="text-xs text-farm-300">เจ้าของฟาร์ม</p>
            </div>}
            {!collapsed && <ArrowUpRight size={16} className="text-farm-300" />}
          </div>
        </div>
      </div>
    </aside>
  );
}

export default Sidebar;
