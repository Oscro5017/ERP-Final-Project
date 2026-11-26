import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import StockDocumentForm from './StockDocumentForm';
import { api, getRole } from '../lib/api';
import { fetchAll } from '../lib/lookups';

const { ask } = vi.hoisted(() => ({ ask: vi.fn() }));
vi.mock('../lib/api', () => ({ api: vi.fn(), getRole: vi.fn() }));
vi.mock('../lib/lookups', () => ({ fetchAll: vi.fn() }));
vi.mock('./AutomationPrompt', () => ({ useAutomation: () => ({ ask }) }));

const lettuce = { id: 1, name: 'ผักกาด', category: 'vegetable', unit: 'kg', on_hand: 11, is_active: true };
const order = (unitPrice = '50') => ({
  id: 9,
  order_no: 'SO-1',
  customer_id: 5,
  customer_name: 'ร้านเอ',
  is_masked: false,
  lines: [{ id: 3, product_id: 1, unit: 'kg', quantity: 8, delivered_quantity: 0, unit_price: unitPrice, has_price: true, delivery_date: '2026-12-01' }],
});

function serve({ role = 'owner', lastPrices = [{ product_id: 1, unit: 'kg', unit_price: '40' }], openOrder = order() } = {}) {
  getRole.mockReturnValue(role);
  fetchAll.mockImplementation(async (path) => ({
    '/products': [lettuce],
    '/suppliers': [],
    '/sales-orders?status=open': [openOrder],
  })[path]);
  api.mockImplementation(async (path, options) => {
    if (options?.method === 'POST') return { doc_no: 'OUT-1', warnings: [] };
    if (path === '/customers') return [{ id: 5, name: 'ร้านเอ' }];
    if (path === '/crop-cycles') return [];
    if (path.startsWith('/trade/last-prices')) return role === 'owner' ? lastPrices : [];
    throw new Error(`unexpected ${path}`);
  });
}

const posted = () => {
  const call = api.mock.calls.find(([, options]) => options?.method === 'POST');
  return call && { path: call[0], body: JSON.parse(call[1].body) };
};

const renderForm = (props = {}) => {
  const onSaved = vi.fn();
  render(<StockDocumentForm docType="outbound" onClose={vi.fn()} onSaved={onSaved} {...props} />);
  return onSaved;
};

async function pickLettuce(user) {
  await user.click(await screen.findByRole('combobox', { name: 'ของ' }));
  await user.click(screen.getByRole('option', { name: /ผักกาด/ }));
}

beforeEach(() => {
  vi.clearAllMocks();
  ask.mockResolvedValue('auto');
});

describe('delivering an order', () => {
  it('fills what is left with the agreed price and asks before finance and closing', async () => {
    serve();
    const user = userEvent.setup();
    const onSaved = renderForm({ initialOrderId: 9 });

    expect(await screen.findByText(/คงเหลือ 11 → 3 kg/)).toBeInTheDocument();
    expect(screen.getByText('ยอดรวม 400.00 บาท')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'บันทึกและตัดสต็อก' }));

    await waitFor(() => expect(onSaved).toHaveBeenCalledWith('บันทึกเอกสาร OUT-1 แล้ว'));
    expect(ask.mock.calls.map(([key]) => key)).toEqual(['order_fill', 'outbound_finance', 'order_close']);
    expect(posted()).toEqual({
      path: '/sales-orders/9/deliver',
      body: expect.objectContaining({
        record_finance: true,
        close_when_complete: true,
        lines: [{ line_id: 3, quantity: '8', unit_price: '50', use_order_price: false }],
      }),
    });
  });

  it('leaves quantities empty when the user fills them in', async () => {
    serve();
    ask.mockResolvedValue('manual');
    const user = userEvent.setup();
    renderForm({ initialOrderId: 9 });

    expect(await screen.findByText(/ค้างส่ง 8 kg/)).toBeInTheDocument();
    expect(screen.getByLabelText('จำนวน')).toHaveValue(null);
    await user.click(screen.getByRole('button', { name: 'บันทึกและตัดสต็อก' }));

    expect(screen.getByRole('alert')).toHaveTextContent('กรุณาระบุปริมาณอย่างน้อย 1 รายการ');
    expect(posted()).toBeUndefined();
  });

  it('lets a developer deliver at the hidden order price without seeing it', async () => {
    serve({ role: 'developer', openOrder: order('gAAAAA-ciphertext') });
    const user = userEvent.setup();
    const onSaved = renderForm({ initialOrderId: 9 });

    expect(await screen.findByText('ยอดรวมตามราคาในออเดอร์')).toBeInTheDocument();
    expect(screen.getByLabelText('ราคาต่อหน่วย (บาท)')).toHaveValue(null);
    expect(screen.queryByText(/ciphertext/)).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'บันทึกและตัดสต็อก' }));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(posted().body.lines).toEqual([{ line_id: 3, quantity: '8', unit_price: null, use_order_price: true }]);
  });

  it('cancels saving when the finance question is closed', async () => {
    serve();
    const user = userEvent.setup();
    renderForm({ initialOrderId: 9 });
    await screen.findByText(/คงเหลือ 11 → 3 kg/);

    ask.mockResolvedValue(null);
    await user.click(screen.getByRole('button', { name: 'บันทึกและตัดสต็อก' }));
    await waitFor(() => expect(ask).toHaveBeenCalledWith('outbound_finance', expect.any(String)));
    expect(posted()).toBeUndefined();
  });
});

describe('selling', () => {
  it('suggests the last price and converts it with the unit', async () => {
    serve();
    const user = userEvent.setup();
    const onSaved = renderForm();
    await pickLettuce(user);
    const price = screen.getByLabelText('ราคาต่อหน่วย (บาท)');
    expect(price).toHaveValue(40);

    await user.selectOptions(screen.getByLabelText('หน่วย'), 'g');
    expect(price).toHaveValue(0.04);
    await user.type(screen.getByLabelText('จำนวน'), '500');

    expect(screen.getByText(/คงเหลือ 11 → 10.5 kg/)).toBeInTheDocument();
    expect(screen.getByText('ยอดรวม 20.00 บาท')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'บันทึกและตัดสต็อก' }));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(posted()).toEqual({
      path: '/trade/outbound',
      body: expect.objectContaining({
        purpose: 'sale',
        record_finance: true,
        lines: [{ product_id: 1, quantity: '500', unit: 'g', unit_price: '0.04' }],
      }),
    });
  });

  it('drops a converted price that cannot be stored to the satang', async () => {
    serve({ lastPrices: [] });
    const user = userEvent.setup();
    renderForm();
    await pickLettuce(user);
    const price = screen.getByLabelText('ราคาต่อหน่วย (บาท)');
    await user.type(price, '33.33');

    await user.selectOptions(screen.getByLabelText('หน่วย'), 'g');
    expect(price).toHaveValue(null);
  });

  it('warns when stock is not enough', async () => {
    serve();
    const user = userEvent.setup();
    renderForm();
    await pickLettuce(user);
    await user.type(screen.getByLabelText('จำนวน'), '12');
    expect(screen.getByText(/คงเหลือ 11 → -1 kg \(ไม่พอ\)/)).toBeInTheDocument();
  });
});

describe('sending out for another reason', () => {
  it('needs a reason and does not ask about income', async () => {
    serve();
    const user = userEvent.setup();
    const onSaved = renderForm();
    await user.click(await screen.findByRole('radio', { name: 'อื่น ๆ' }));
    await pickLettuce(user);
    await user.type(screen.getByLabelText('จำนวน'), '1');

    await user.click(screen.getByRole('button', { name: 'บันทึกและตัดสต็อก' }));
    expect(screen.getByRole('alert')).toHaveTextContent('กรุณาระบุเหตุผลที่ส่งออก');

    await user.type(screen.getByLabelText('เหตุผล (จำเป็น)'), 'แจกตัวอย่าง');
    await user.click(screen.getByRole('button', { name: 'บันทึกและตัดสต็อก' }));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(ask).not.toHaveBeenCalled();
    expect(posted().body).toEqual(expect.objectContaining({ purpose: 'other', record_finance: false, note: 'แจกตัวอย่าง' }));
  });
});

describe('receiving', () => {
  it('adds to stock and asks about the expense', async () => {
    serve();
    const user = userEvent.setup();
    const onSaved = renderForm({ docType: 'inbound' });
    await pickLettuce(user);
    await user.type(screen.getByLabelText('จำนวน'), '2');
    expect(screen.getByText(/คงเหลือ 11 → 13 kg/)).toBeInTheDocument();

    ask.mockResolvedValue('manual');
    await user.click(screen.getByRole('button', { name: 'บันทึกและรับเข้าคลัง' }));
    await waitFor(() => expect(onSaved).toHaveBeenCalledWith('บันทึกเอกสาร OUT-1 แล้ว · ยังไม่ลงบัญชี'));
    expect(ask).toHaveBeenCalledWith('inbound_finance', 'ยอดรวม 80.00 บาท');
    expect(posted()).toEqual({ path: '/trade/inbound', body: expect.objectContaining({ record_finance: false, supplier_id: null }) });
  });
});
