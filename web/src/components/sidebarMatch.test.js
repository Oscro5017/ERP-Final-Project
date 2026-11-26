import { describe, expect, it } from 'vitest';
import { activeMenuItem } from './sidebarMatch';

const items = [
  { name: 'รอบปลูก', to: '/plots' },
  { name: 'ผลผลิต', to: '/plots?status=harvested' },
  { name: 'พยากรณ์', to: '/weather#forecast' },
  { name: 'บันทึกย้อนหลัง', to: '/weather#history' },
];
const at = (pathname, search = '', hash = '') => activeMenuItem(items, { pathname, search, hash })?.name;

describe('activeMenuItem', () => {
  it('picks the entry whose query matches', () => {
    expect(at('/plots', '?status=harvested')).toBe('ผลผลิต');
    expect(at('/plots')).toBe('รอบปลูก');
    expect(at('/plots', '?status=nursery')).toBe('รอบปลูก');
  });

  it('picks the entry whose hash matches', () => {
    expect(at('/weather', '', '#history')).toBe('บันทึกย้อนหลัง');
    expect(at('/weather', '', '#forecast')).toBe('พยากรณ์');
    expect(at('/weather')).toBe('พยากรณ์');
  });

  it('highlights nothing on other pages', () => {
    expect(at('/plots/3')).toBeUndefined();
  });
});
