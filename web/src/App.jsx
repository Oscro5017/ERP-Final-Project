import { lazy, Suspense, useState } from 'react';
import { Routes, Route, Navigate, Link } from 'react-router-dom';
import DashboardLayout from './layouts/DashboardLayout';
import Login from './pages/Login';
import { AutomationProvider } from './components/AutomationPrompt';
import { DialogProvider } from './components/DialogProvider';
import { clearToken, getToken } from './lib/api';

// Each page loads when it is first opened, so the first screen downloads less.
const Dashboard = lazy(() => import('./pages/Dashboard'));
const Weather = lazy(() => import('./pages/farm/Weather'));
const FarmPlots = lazy(() => import('./pages/farm/FarmPlots'));
const PlotDetail = lazy(() => import('./pages/farm/PlotDetail'));
const Activities = lazy(() => import('./pages/farm/Activities'));
const Warehouse = lazy(() => import('./pages/warehouse/Warehouse'));
const Sales = lazy(() => import('./pages/sales/Sales'));
const Settings = lazy(() => import('./pages/Settings'));
const Finance = lazy(() => import('./pages/finance/Finance'));
const Suppliers = lazy(() => import('./pages/warehouse/Suppliers'));
const Insights = lazy(() => import('./pages/finance/Insights'));
const CustomerPanel = lazy(() => import('./components/CustomerPanel'));

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
    <DialogProvider>
    <AutomationProvider>
    <DashboardLayout onLogout={handleLogout}>
      <Suspense fallback={<p className="py-16 text-center text-sm text-slate-500">กำลังโหลด…</p>}>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/weather" element={<Weather />} />
        <Route path="/plots" element={<FarmPlots />} />
        <Route path="/plots/:id" element={<PlotDetail />} />
        <Route path="/activities" element={<Activities />} />
        <Route path="/harvest" element={<Navigate to="/plots?status=harvested" replace />} />
        <Route path="/warehouse/*" element={<Warehouse />} />
        <Route path="/sales/*" element={<Sales />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/fresh-stock" element={<Navigate to="/warehouse/fresh" replace />} />
        <Route path="/orders" element={<Navigate to="/sales/orders" replace />} />
        <Route path="/products" element={<Navigate to="/warehouse/items" replace />} />
        <Route path="/stock" element={<Navigate to="/warehouse/items" replace />} />
        <Route path="/trade" element={<Navigate to="/warehouse/documents" replace />} />
        <Route path="/finance" element={<Finance />} />
        <Route path="/partners/customers" element={<CustomerPanel />} />
        <Route path="/partners/suppliers" element={<Suppliers />} />
        <Route path="/insights" element={<Insights />} />
        <Route path="*" element={<NotFound />} />
      </Routes>
      </Suspense>
    </DashboardLayout>
    </AutomationProvider>
    </DialogProvider>
  );
}

export default App;
