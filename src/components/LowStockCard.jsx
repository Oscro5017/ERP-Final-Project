import { AlertTriangle } from 'lucide-react';
import StatusBadge from './StatusBadge';

function LowStockCard({ item }) {
  return (
    <div className="flex items-center justify-between rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex items-center gap-3">
        <div className="rounded-full bg-rose-100 p-2 text-rose-600">
          <AlertTriangle size={18} />
        </div>
        <div>
          <p className="font-semibold text-slate-800">{item.name}</p>
          <p className="text-sm text-slate-500">เหลือ {item.stock} {item.unit}</p>
        </div>
      </div>
      <StatusBadge status={item.status} />
    </div>
  );
}

export default LowStockCard;
