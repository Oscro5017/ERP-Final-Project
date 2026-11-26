import { Navigate, Route, Routes } from 'react-router-dom';
import SectionTabs from '../components/SectionTabs';
import FreshStock from './FreshStock';
import Products from './Products';
import Stock from './Stock';
import TradeDocuments from './TradeDocuments';

const tabs = [
  ['/warehouse/items', 'รายการของ'],
  ['/warehouse/fresh', 'ของสด'],
  ['/warehouse/documents', 'รับเข้า-ส่งออก'],
  ['/warehouse/history', 'ประวัติ'],
];

function Warehouse() {
  return (
    <div className="space-y-6">
      <SectionTabs label="คลัง" tabs={tabs} />
      <Routes>
        <Route path="items" element={<Products />} />
        <Route path="fresh" element={<FreshStock />} />
        <Route path="documents" element={<TradeDocuments key="documents" />} />
        <Route path="history" element={<Stock />} />
        <Route path="*" element={<Navigate to="/warehouse/items" replace />} />
      </Routes>
    </div>
  );
}

export default Warehouse;
