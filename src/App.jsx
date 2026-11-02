import { useState } from 'react';
import { Routes, Route } from 'react-router-dom';
import DashboardLayout from './layouts/DashboardLayout';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import Weather from './pages/Weather';
import FarmPlots from './pages/FarmPlots';
import PlotDetail from './pages/PlotDetail';
import Activities from './pages/Activities';
import Harvest from './pages/Harvest';
import Inventory from './pages/Inventory';
import Sales from './pages/Sales';
import Costs from './pages/Costs';
import Reports from './pages/Reports';
import Users from './pages/Users';
import Settings from './pages/Settings';
import { clearToken, getToken } from './lib/api';

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
        <Route path="/harvest" element={<Harvest />} />
        <Route path="/inventory" element={<Inventory />} />
        <Route path="/sales" element={<Sales />} />
        <Route path="/costs" element={<Costs />} />
        <Route path="/reports" element={<Reports />} />
        <Route path="/users" element={<Users />} />
        <Route path="/settings" element={<Settings />} />
      </Routes>
    </DashboardLayout>
  );
}

export default App;
