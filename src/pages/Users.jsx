import { userData } from '../data/mockData';

function Users() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-slate-800">ผู้ใช้งาน</h1>
        <p className="text-sm text-slate-500">จัดการข้อมูลผู้ใช้งานและสิทธิ์การเข้าถึง</p>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        {userData.map((user) => (
          <div key={user.name} className="rounded-2xl border border-slate-200 bg-white p-5 shadow-soft">
            <p className="font-semibold text-slate-800">{user.name}</p>
            <p className="mt-1 text-sm text-slate-500">{user.role}</p>
            <div className="mt-3 flex items-center justify-between text-sm">
              <span className="text-slate-500">กะ {user.shift}</span>
              <span className="font-semibold text-emerald-700">{user.status}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default Users;
