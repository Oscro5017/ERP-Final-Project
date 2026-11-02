import { useState } from 'react';
import { Leaf, LockKeyhole, UserRound } from 'lucide-react';
import { login } from '../lib/api';

function Login({ onLogin, initialError = '' }) {
  const [username, setUsername] = useState('owner');
  const [password, setPassword] = useState('owner123');
  const [error, setError] = useState(initialError);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (event) => {
    event.preventDefault();
    setError('');
    setIsSubmitting(true);
    try {
      const data = await login(username, password);
      onLogin(data);
    } catch (loginError) {
      setError(loginError.message);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-100 px-4 py-8">
      <section className="w-full max-w-md rounded-3xl border border-slate-200 bg-white p-8 shadow-soft">
        <div className="mb-8 flex items-center gap-3">
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-farm-700 text-white">
            <Leaf size={24} />
          </div>
          <div>
            <p className="text-lg font-bold text-slate-800">Organic Farm</p>
            <p className="text-sm text-slate-500">ระบบจัดการฟาร์ม</p>
          </div>
        </div>
        <h1 className="text-2xl font-semibold text-slate-800">เข้าสู่ระบบ</h1>
        <p className="mt-2 text-sm text-slate-500">จัดการข้อมูลฟาร์มของคุณในที่เดียว</p>
        <form onSubmit={handleSubmit} className="mt-6 space-y-4">
          <label className="block text-sm font-medium text-slate-700">
            ชื่อผู้ใช้
            <span className="mt-2 flex items-center gap-2 rounded-xl border border-slate-200 px-3 py-2.5">
              <UserRound size={17} className="text-slate-400" />
              <input value={username} onChange={(event) => setUsername(event.target.value)} className="w-full outline-none" autoComplete="username" required />
            </span>
          </label>
          <label className="block text-sm font-medium text-slate-700">
            รหัสผ่าน
            <span className="mt-2 flex items-center gap-2 rounded-xl border border-slate-200 px-3 py-2.5">
              <LockKeyhole size={17} className="text-slate-400" />
              <input value={password} onChange={(event) => setPassword(event.target.value)} className="w-full outline-none" type="password" autoComplete="current-password" required />
            </span>
          </label>
          {error && <p className="text-sm text-rose-600">{error}</p>}
          <button disabled={isSubmitting} className="w-full rounded-xl bg-farm-700 px-4 py-3 text-sm font-semibold text-white transition hover:bg-farm-800 disabled:cursor-not-allowed disabled:opacity-60">
            {isSubmitting ? 'กำลังเข้าสู่ระบบ...' : 'เข้าสู่ระบบ'}
          </button>
        </form>
      </section>
    </main>
  );
}

export default Login;
