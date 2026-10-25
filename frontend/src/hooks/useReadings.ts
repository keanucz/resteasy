import { useEffect, useState } from 'react';

import { fetchReadings, type Reading } from '@/services/readings';
import { supabase } from '@/services/supabase/client';

/** How often a night still in progress re-reads its readings. */
const LIVE_REFRESH_MS = 60_000;

/**
 * The pillow's readings between `from` and `to`. A night still in progress (`live`) follows them
 * through Realtime and re-reads every minute as a fallback; a past night reads once.
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
    // While the night is live, the backend rewrites the current minute every few seconds: fold each
    // change straight into the rows instead of re-reading the whole night.
    const channel = live
      ? supabase
          .channel(`readings:${pillowId}`)
          .on(
            'postgres_changes',
            { event: '*', schema: 'public', table: 'readings', filter: `pillow_id=eq.${pillowId}` },
            (payload) => {
              const row = payload.new as Partial<Reading>;
              if (cancelled || !row.ts) return;
              const t = Date.parse(row.ts);
              if (t < from || t >= to) return;
              const reading: Reading = {
                ts: row.ts,
                temp_c: row.temp_c ?? null,
                head_on: row.head_on ?? null,
                motion: row.motion ?? null,
              };
              setState((prev) => {
                if (prev?.key !== key) return prev;
                const rows = prev.rows.filter((r) => Date.parse(r.ts) !== t);
                rows.push(reading);
                rows.sort((a, b) => Date.parse(a.ts) - Date.parse(b.ts));
                return { key, rows };
              });
            },
          )
          .subscribe()
      : null;
    return () => {
      cancelled = true;
      if (id) clearInterval(id);
      if (channel) supabase.removeChannel(channel);
    };
  }, [pillowId, from, to, live, key]);

  const rows = state?.key === key ? state.rows : null;
  return { rows: rows ?? [], loading: rows === null };
}
