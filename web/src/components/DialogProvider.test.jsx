import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { DialogProvider, useDialog } from './DialogProvider';

function Probe({ onResult }) {
  const { confirm, alert } = useDialog();
  return (
    <>
      <button type="button" onClick={async () => onResult(await confirm({ message: 'ลบโต๊ะ 3?', confirmLabel: 'ลบ' }))}>ask</button>
      <button type="button" onClick={async () => { await alert('ลบไม่สำเร็จ'); onResult('closed'); }}>tell</button>
    </>
  );
}

const setup = () => {
  const results = [];
  render(<DialogProvider><Probe onResult={(value) => results.push(value)} /></DialogProvider>);
  return { user: userEvent.setup(), results };
};

describe('DialogProvider', () => {
  it('resolves confirm with the button the user picks', async () => {
    const { user, results } = setup();
    await user.click(screen.getByText('ask'));
    expect(screen.getByRole('dialog', { name: 'ยืนยัน' })).toHaveTextContent('ลบโต๊ะ 3?');
    await user.click(screen.getByRole('button', { name: 'ลบ' }));
    await user.click(screen.getByText('ask'));
    await user.click(screen.getByRole('button', { name: 'ยกเลิก' }));
    await user.click(screen.getByText('ask'));
    await user.click(screen.getByRole('button', { name: 'ปิด' }));
    expect(results).toEqual([true, false, false]);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('waits for an alert to be closed', async () => {
    const { user, results } = setup();
    await user.click(screen.getByText('tell'));
    expect(results).toEqual([]);
    await user.click(screen.getByRole('button', { name: 'ตกลง' }));
    expect(results).toEqual(['closed']);
  });
});
