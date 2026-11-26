import { Navigate, Route, Routes } from 'react-router-dom';
import SectionTabs from '../components/SectionTabs';
import Orders from './Orders';
import TradeDocuments from './TradeDocuments';

const tabs = [
  ['/sales/orders', 'ออเดอร์'],
  ['/sales/list', 'รายการขาย'],
];

function Sales() {
  return (
    <div className="space-y-6">
      <SectionTabs label="การขาย" tabs={tabs} />
      <Routes>
        <Route path="orders" element={<Orders />} />
        <Route path="list" element={<TradeDocuments key="sales" salesOnly />} />
        <Route path="*" element={<Navigate to="/sales/orders" replace />} />
      </Routes>
    </div>
  );
}

export default Sales;
