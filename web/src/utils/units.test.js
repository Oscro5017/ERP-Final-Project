import { describe, expect, it } from 'vitest';
import { compatibleUnits, convert } from './units';

describe('compatibleUnits', () => {
  it('offers the other scale in the same language', () => {
    expect(compatibleUnits('kg')).toEqual(['kg', 'g']);
    expect(compatibleUnits('กก.')).toEqual(['กก.', 'กรัม']);
    expect(compatibleUnits('ลิตร')).toEqual(['ลิตร', 'มล.']);
  });

  it('keeps units it does not know as they are', () => {
    expect(compatibleUnits('ถุง')).toEqual(['ถุง']);
  });
});

describe('convert', () => {
  it('converts within a family', () => {
    expect(convert(500, 'g', 'kg')).toBe(0.5);
    expect(convert(1.25, 'kg', 'กรัม')).toBe(1250);
    expect(convert(250, 'ml', 'l')).toBe(0.25);
  });

  it('ignores case and spaces', () => {
    expect(convert(2, ' KG ', 'kg')).toBe(2);
  });

  it('returns null when units do not convert', () => {
    expect(convert(1, 'kg', 'l')).toBeNull();
    expect(convert(1, 'ถุง', 'kg')).toBeNull();
  });

  it('rounds to 3 decimals', () => {
    expect(convert(1, 'g', 'kg')).toBe(0.001);
    expect(convert(0.4, 'g', 'kg')).toBe(0);
  });
});
