import { useEffect, useState } from 'react';
import { Link, NavLink, useLocation } from 'react-router-dom';
import {
  Activity,
  ArrowDownToLine,
  ArrowUpFromLine,
  Boxes,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ClipboardList,
  CloudSun,
  LayoutDashboard,
  Sprout,
  Users,
  Wallet,
} from 'lucide-react';

const navigationGroups = [
  { id: 'farm', name: 'ฟาร์ม', icon: Sprout, children: [
    { name: 'รอบปลูก', to: '/plots' },
    { name: 'กิจกรรม', to: '/activities' },
    { name: 'ผลผลิต', to: '/harvest' },
  ] },
  { id: 'weather', name: 'สภาพอากาศ', icon: CloudSun, children: [
    { name: 'พยากรณ์', to: '/weather#forecast' },
    { name: 'บันทึกย้อนหลัง', to: '/weather#history' },
  ] },
  { id: 'products', name: 'สินค้า & คลัง', icon: Boxes, children: [
    { name: 'สินค้า', disabled: true },
    { name: 'คลังสินค้า', disabled: true },
  ] },
  { id: 'trade', name: 'รับเข้า / ส่งออก', icon: ArrowDownToLine, children: [
    { name: 'รับเข้า', disabled: true },
    { name: 'ส่งออก', disabled: true, icon: ArrowUpFromLine },
  ] },
  { id: 'finance', name: 'การเงิน', icon: Wallet, children: [
    { name: 'ภาพรวม', disabled: true },
    { name: 'รายงาน', disabled: true },
  ] },
  { id: 'partners', name: 'คู่ค้า', icon: Users, children: [
    { name: 'ลูกค้า', to: '/partners/customers' },
    { name: 'ซัพพลายเออร์', disabled: true },
  ] },
];

function Sidebar({ collapsed, onToggle }) {
  const location = useLocation();
  const activeGroup = navigationGroups.find((group) => group.children.some((item) => (
    item.to && location.pathname === item.to.split('#')[0]
  )))?.id;
  const [expandedGroup, setExpandedGroup] = useState(activeGroup || null);

  useEffect(() => {
    if (activeGroup) setExpandedGroup(activeGroup);
  }, [activeGroup]);

  const toggleGroup = (groupId) => {
    if (collapsed) onToggle();
    setExpandedGroup((current) => current === groupId ? null : groupId);
  };

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
          <NavLink
            to="/"
            end
            title={collapsed ? 'ภาพรวม' : undefined}
            className={({ isActive }) => `mb-1 flex items-center gap-3 rounded-xl px-3 py-3 text-sm font-medium transition ${isActive ? 'bg-farm-700 text-white shadow-soft' : 'text-farm-100 hover:bg-farm-800'}`}
          >
            <LayoutDashboard size={18} />
            {!collapsed && <span>ภาพรวม</span>}
          </NavLink>

          {navigationGroups.map((group) => {
            const Icon = group.icon;
            const isExpanded = expandedGroup === group.id;
            const hasActiveChild = group.children.some((item) => item.to && location.pathname === item.to.split('#')[0]);

            return (
              <div key={group.id}>
                <button
                  type="button"
                  title={collapsed ? group.name : undefined}
                  aria-expanded={!collapsed && isExpanded}
                  onClick={() => toggleGroup(group.id)}
                  className={`mb-1 flex w-full items-center gap-3 rounded-xl px-3 py-3 text-left text-sm font-medium transition ${hasActiveChild ? 'bg-farm-700 text-white' : 'text-farm-100 hover:bg-farm-800'}`}
                >
                  <Icon size={18} />
                  {!collapsed && <>
                    <span className="flex-1">{group.name}</span>
                    <ChevronDown size={15} className={`transition-transform ${isExpanded ? 'rotate-180' : ''}`} />
                  </>}
                </button>

                {!collapsed && isExpanded && (
                  <div className="mb-2 ml-6 border-l border-farm-700/70 py-1 pl-3">
                    {group.children.map((item) => {
                      const ChildIcon = item.icon;
                      if (item.disabled) {
                        return (
                          <div key={item.name} aria-disabled="true" className="flex cursor-not-allowed items-center justify-between gap-2 rounded-lg px-3 py-2 text-sm text-farm-300/60">
                            <span className="flex items-center gap-2">{ChildIcon && <ChildIcon size={14} />}{item.name}</span>
                            <span className="text-[10px]">ยังไม่พร้อม</span>
                          </div>
                        );
                      }

                      return (
                        <NavLink
                          key={item.to}
                          to={item.to}
                          end={!item.to.includes('#')}
                          className={({ isActive }) => `mb-1 flex items-center gap-2 rounded-lg px-3 py-2 text-sm transition ${isActive ? 'bg-farm-800 text-white' : 'text-farm-100 hover:bg-farm-800/70'}`}
                        >
                          {ChildIcon && <ChildIcon size={14} />}
                          {item.name}
                        </NavLink>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
        </nav>

      </div>
    </aside>
  );
}

export default Sidebar;
