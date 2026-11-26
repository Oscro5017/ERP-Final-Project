import { api } from './api';

const PAGE = 200;

/** Every item of a paged list endpoint. */
export async function fetchAll(path) {
  const items = [];
  const separator = path.includes('?') ? '&' : '?';
  for (;;) {
    const data = await api(`${path}${separator}limit=${PAGE}&offset=${items.length}`);
    items.push(...data.items);
    if (!data.items.length || items.length >= data.total) return items;
  }
}
