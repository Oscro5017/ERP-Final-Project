// Which sidebar entry matches the current URL. Entries can share a path and differ by query or hash,
// e.g. รอบปลูก (/plots) and ผลผลิต (/plots?status=harvested), so the most specific match wins.

const parse = (to) => {
  const [beforeHash, hash = ''] = to.split('#');
  const [path, query = ''] = beforeHash.split('?');
  return { path, params: [...new URLSearchParams(query)], hash: hash ? `#${hash}` : '' };
};

/** The entry is for the page being shown, whatever its query or hash. */
export const onMenuPath = (item, location) => Boolean(item.to) && parse(item.to).path === location.pathname;

function score(item, location) {
  if (!onMenuPath(item, location)) return -1;
  const { params, hash } = parse(item.to);
  const current = new URLSearchParams(location.search);
  if (params.some(([key, value]) => current.get(key) !== value)) return -1;
  if (hash && location.hash && hash !== location.hash) return -1;
  return params.length + (hash && hash === location.hash ? 1 : 0);
}

/** The single entry to highlight, or undefined when no entry matches. */
export function activeMenuItem(items, location) {
  let best;
  let bestScore = -1;
  for (const item of items) {
    const value = score(item, location);
    if (value > bestScore) {
      best = item;
      bestScore = value;
    }
  }
  return best;
}
