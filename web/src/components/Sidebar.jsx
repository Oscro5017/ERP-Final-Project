import { useEffect, useState } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import {
  Boxes,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ClipboardList,
  CloudSun,
  LayoutDashboard,
  Lightbulb,
  Settings,
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
  { id: 'warehouse', name: 'คลัง', icon: Boxes, children: [
    { name: 'รายการของ', to: '/warehouse/items' },
    { name: 'ของสด', to: '/warehouse/fresh' },
    { name: 'รับเข้า-ส่งออก', to: '/warehouse/documents' },
    { name: 'ประวัติ', to: '/warehouse/history' },
  ] },
  { id: 'sales', name: 'การขาย', icon: ClipboardList, children: [
    { name: 'ออเดอร์', to: '/sales/orders' },
    { name: 'รายการขาย', to: '/sales/list' },
  ] },
  { id: 'finance', name: 'การเงิน', icon: Wallet, children: [
    { name: 'ภาพรวม', to: '/finance' },
    { name: 'รายงาน', disabled: true },
  ] },
  { id: 'partners', name: 'คู่ค้า', icon: Users, children: [
    { name: 'ลูกค้า', to: '/partners/customers' },
    { name: 'ซัพพลายเออร์', to: '/partners/suppliers' },
  ] },
  { id: 'insights', name: 'ข้อมูลเชิงลึก', icon: Lightbulb, children: [
    { name: 'คำแนะนำ', to: '/insights' },
  ] },
  { id: 'settings', name: 'ตั้งค่า', icon: Settings, children: [
    { name: 'การทำงานอัตโนมัติ', to: '/settings' },
  ] },
];

function Sidebar({ collapsed, mobileOpen, onToggle, onNavigate }) {
  const isCollapsed = collapsed && !mobileOpen;
  const location = useLocation();
  const activeGroup = navigationGroups.find((group) => group.children.some((item) => (
    item.to && location.pathname === item.to.split('#')[0]
  )))?.id;
  const [expandedGroup, setExpandedGroup] = useState(activeGroup || null);

  useEffect(() => {
    if (activeGroup) setExpandedGroup(activeGroup);
  }, [activeGroup]);

  const toggleGroup = (groupId) => {
    if (isCollapsed) onToggle();
    setExpandedGroup((current) => current === groupId ? null : groupId);
  };

  return (
    <aside className={`fixed left-0 top-0 z-40 h-dvh border-r border-farm-700/20 bg-farm-900 text-white shadow-xl shadow-slate-950/10 transition-[width,transform] duration-300 md:translate-x-0 md:shadow-none ${mobileOpen ? 'translate-x-0' : '-translate-x-full'} ${isCollapsed ? 'md:w-[76px]' : 'w-[min(82vw,280px)] md:w-64 xl:w-72'}`}>
      <div className="flex h-full flex-col">
        <div className={`flex min-h-[88px] items-center border-b border-white/10 px-4 ${isCollapsed ? 'flex-col justify-center gap-2 py-3' : 'justify-between py-5'}`}>
          <div className={`flex min-w-0 items-center ${isCollapsed ? '' : 'gap-3'}`}>
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-farm-700/80 text-farm-50">
              <Sprout size={20} aria-hidden="true" />
            </div>
            {!isCollapsed && <div className="min-w-0">
              <p className="truncate text-sm font-semibold tracking-[0.01em]">Organic Farm</p>
              <p className="truncate text-xs text-farm-300">Management System</p>
            </div>}
          </div>
          <button onClick={onToggle} aria-label={isCollapsed ? 'ขยายเมนู' : 'ย่อเมนู'} title={isCollapsed ? 'ขยายเมนู' : 'ย่อเมนู'} className={`hidden h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-white/10 bg-white/5 text-farm-200 transition hover:border-white/20 hover:bg-white/10 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-farm-300 md:inline-flex ${isCollapsed ? '' : 'ml-1'}`}>
            {isCollapsed ? <ChevronRight size={17} /> : <ChevronLeft size={17} />}
          </button>
        </div>

        <nav aria-label="เมนูหลัก" className={`mt-3 flex-1 overflow-y-auto pb-4 ${isCollapsed ? 'px-2' : 'px-3'}`}>
          <NavLink
            to="/"
            end
            title={isCollapsed ? 'ภาพรวม' : undefined}
            className={({ isActive }) => `mb-1.5 flex min-h-11 items-center rounded-xl text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-farm-300 ${isCollapsed ? 'justify-center px-0' : 'gap-3 px-3'} ${isActive ? 'bg-farm-700 text-white shadow-soft' : 'text-farm-100 hover:bg-farm-800'}`}
            onClick={onNavigate}
          >
            <LayoutDashboard size={18} aria-hidden="true" />
            {!isCollapsed && <span>ภาพรวม</span>}
          </NavLink>

          {navigationGroups.map((group) => {
            const Icon = group.icon;
            const isExpanded = expandedGroup === group.id;
            const hasActiveChild = group.children.some((item) => item.to && location.pathname === item.to.split('#')[0]);

            return (
              <div key={group.id}>
                <button
                  type="button"
                  title={isCollapsed ? group.name : undefined}
                  aria-expanded={!isCollapsed && isExpanded}
                  onClick={() => toggleGroup(group.id)}
                  className={`mb-1.5 flex min-h-11 w-full items-center rounded-xl text-left text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-farm-300 ${isCollapsed ? 'justify-center px-0' : 'gap-3 px-3'} ${hasActiveChild ? 'bg-farm-700 text-white' : 'text-farm-100 hover:bg-farm-800'}`}
                >
                  <Icon size={18} aria-hidden="true" />
                  {!isCollapsed && <>
                    <span className="flex-1">{group.name}</span>
                    <ChevronDown size={15} className={`transition-transform ${isExpanded ? 'rotate-180' : ''}`} />
                  </>}
                </button>

                {!isCollapsed && isExpanded && (
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
                          key={item.name}
                          to={item.to}
                          end={!item.to.includes('#')}
                          onClick={onNavigate}
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
