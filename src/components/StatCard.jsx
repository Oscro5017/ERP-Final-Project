function StatCard({ title, value, change, icon: Icon, tone = 'green' }) {
  const tones = {
    green: 'bg-farm-50 text-farm-700',
    yellow: 'bg-amber-50 text-amber-600',
    blue: 'bg-sky-50 text-sky-600',
    red: 'bg-rose-50 text-rose-600',
  };

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-soft">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm text-slate-500">{title}</p>
          <p className="mt-2 text-2xl font-semibold text-slate-800">{value}</p>
        </div>
        <div className={`rounded-xl p-3 ${tones[tone]}`}>
          {Icon && <Icon size={20} />}
        </div>
      </div>
      <p className="mt-4 text-sm text-emerald-600">{change}</p>
    </div>
  );
}

export default StatCard;
