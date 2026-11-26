import { describe, expect, it } from 'vitest';
import { formatMoney, formatNumber, formatQuantity } from './format';
import { MASKED_TEXT, maskedField, readAmount } from './masking';

describe('format', () => {
  it('shows prices with two decimals', () => {
    expect(formatNumber(1234.5)).toBe('1,234.50');
    expect(formatNumber('40')).toBe('40.00');
    expect(formatMoney('1234.5')).toBe('1,234.50 ฿');
  });

  it('shows quantities without trailing zeros', () => {
    expect(formatQuantity(10.5)).toBe('10.5');
    expect(formatQuantity('0.125')).toBe('0.125');
    expect(formatQuantity(3)).toBe('3');
  });

  it('shows a dash when there is no value', () => {
    for (const value of [null, undefined, '']) {
      expect(formatNumber(value)).toBe('-');
      expect(formatQuantity(value)).toBe('-');
      expect(formatMoney(value)).toBe('-');
    }
  });

  it('passes ciphertext through unchanged', () => {
    expect(formatMoney('gAAAAAB-token')).toBe('gAAAAAB-token');
  });
});

describe('masking', () => {
  it('reads plain and wrapped amounts', () => {
    expect(readAmount('50')).toEqual({ value: '50', isMasked: false });
    expect(readAmount({ value: '50', is_masked: true })).toEqual({ value: '50', isMasked: true });
    expect(readAmount(null, { is_masked: true })).toEqual({ value: null, isMasked: true });
    expect(readAmount({ value: '7' }, { is_masked: true })).toEqual({ value: '7', isMasked: true });
  });

  it('hides fields of masked records', () => {
    expect(maskedField({ is_masked: true, name: 'gAAAA' }, 'name')).toBe(MASKED_TEXT);
    expect(maskedField({ is_masked: false, name: 'ผักกาด' }, 'name')).toBe('ผักกาด');
  });
});
