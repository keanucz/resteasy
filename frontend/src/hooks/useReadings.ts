import { useEffect, useState } from 'react';

import { fetchReadings, type Reading } from '@/services/readings';

/** How often a night still in progress re-reads its readings. */
const LIVE_REFRESH_MS = 60_000;

/**
 * The pillow's readings between `from` and `to`. A night still in progress (`live`) re-reads them
 * every minute; a past night reads once.
 */
export function useReadings(pillowId: string | null, from: number, to: number, live: boolean) {
  const key = `${pillowId}:${from}:${to}`;
  const [state, setState] = useState<{ key: string; rows: Reading[] } | null>(null);

  useEffect(() => {
    if (!pillowId) return;
    let cancelled = false;
    const read = () =>
      fetchReadings(pillowId, from, to).then((rows) => {
        // Same rows as before: keep the old array, so the charts don't redraw for nothing.
        if (!cancelled)
          setState((prev) => (prev?.key === key && prev.rows.length === rows.length ? prev : { key, rows }));
      });
    read();
    const id = live ? setInterval(read, LIVE_REFRESH_MS) : undefined;
    return () => {
      cancelled = true;
      if (id) clearInterval(id);
    };
  }, [pillowId, from, to, live, key]);

  const rows = state?.key === key ? state.rows : null;
  return { rows: rows ?? [], loading: rows === null };
}
