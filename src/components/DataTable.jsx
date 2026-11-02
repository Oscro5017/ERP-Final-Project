import { ArrowUpDown, Eye, Pencil, Trash2 } from 'lucide-react';

function DataTable({ columns, rows, actions = true, onView, onEdit, onDelete }) {
  return (
    <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-soft">
      <div className="overflow-x-auto">
        <table className="min-w-full text-left text-sm">
          <thead className="bg-slate-50 text-slate-600">
            <tr>
              {columns.map((column) => (
                <th key={column.key} className="px-4 py-3 font-semibold">
                  <div className="flex items-center gap-2">
                    <span>{column.label}</span>
                    {column.sortable && <ArrowUpDown size={14} className="text-slate-400" />}
                  </div>
                </th>
              ))}
              {actions && <th className="px-4 py-3 font-semibold">จัดการ</th>}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={index} className="border-t border-slate-100 hover:bg-slate-50">
                {columns.map((column) => (
                  <td key={column.key} className="px-4 py-3 text-slate-700">
                    {row[column.key]}
                  </td>
                ))}
                {actions && (
                  <td className="px-4 py-3">
                    <div className="flex gap-2">
                      <button onClick={() => onView?.(row)} className="rounded-lg border border-slate-200 p-2 text-slate-600 hover:bg-slate-100"><Eye size={15} /></button>
                      <button onClick={() => onEdit?.(row)} className="rounded-lg border border-slate-200 p-2 text-slate-600 hover:bg-slate-100"><Pencil size={15} /></button>
                      <button onClick={() => onDelete?.(row)} className="rounded-lg border border-slate-200 p-2 text-rose-600 hover:bg-rose-50"><Trash2 size={15} /></button>
                    </div>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default DataTable;
