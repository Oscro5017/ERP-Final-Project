import { NavLink } from 'react-router-dom';

/** Sub-pages of one section. tabs: [[path, label]] */
function SectionTabs({ label, tabs }) {
  return (
    <nav aria-label={label} className="flex gap-1 overflow-x-auto border-b border-slate-200">
      {tabs.map(([to, name]) => (
        <NavLink key={to} to={to} className={({ isActive }) => `whitespace-nowrap border-b-2 px-4 py-2.5 text-sm font-semibold ${isActive ? 'border-farm-700 text-farm-800' : 'border-transparent text-slate-500 hover:text-slate-800'}`}>{name}</NavLink>
      ))}
    </nav>
  );
}

export default SectionTabs;
