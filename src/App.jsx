import { useState } from 'react';
import { Routes, Route, Navigate, Link } from 'react-router-dom';
import DashboardLayout from './layouts/DashboardLayout';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import Weather from './pages/Weather';
import FarmPlots from './pages/FarmPlots';
import PlotDetail from './pages/PlotDetail';
import Activities from './pages/Activities';
import CustomerPanel from './components/CustomerPanel';
import { clearToken, getToken } from './lib/api';

function NotFound() {
  return (
    <section className="py-16 text-center">
      <h1 className="text-xl font-semibold text-slate-800">ไม่พบหน้านี้</h1>
      <Link to="/" className="mt-4 inline-flex rounded-lg bg-farm-700 px-4 py-2 text-sm font-medium text-white hover:bg-farm-800">
        กลับหน้าภาพรวม
      </Link>
    </section>
  );
}

function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(Boolean(getToken()));
  const sessionExpired = new URLSearchParams(window.location.search).get('sessionExpired') === '1';

  if (!isAuthenticated) {
    return <Login onLogin={() => setIsAuthenticated(true)} initialError={sessionExpired ? 'เซสชันหมดอายุ กรุณาเข้าสู่ระบบใหม่' : ''} />;
  }

  const handleLogout = () => {
    clearToken();
    setIsAuthenticated(false);
  };

  return (
    <DashboardLayout onLogout={handleLogout}>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/weather" element={<Weather />} />
        <Route path="/plots" element={<FarmPlots />} />
        <Route path="/plots/:id" element={<PlotDetail />} />
        <Route path="/activities" element={<Activities />} />
        <Route path="/harvest" element={<Navigate to="/plots?status=harvested" replace />} />
        <Route path="/partners/customers" element={<CustomerPanel />} />
        <Route path="*" element={<NotFound />} />
      </Routes>
    </DashboardLayout>
  );
}

export default App;
