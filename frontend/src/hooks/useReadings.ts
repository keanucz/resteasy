import { useEffect, useState } from 'react';

import { fetchReadings, type Reading } from '@/services/readings';
import { supabase } from '@/services/supabase/client';

/** How often a night still in progress re-reads its readings. */
const LIVE_REFRESH_MS = 60_000;
/** Live readings arrive every few seconds; the charts take them in at most this often. */
const LIVE_FLUSH_MS = 5000;
/** A read that hasn't answered by now counts as failed, so the next tick can try again. */
const READ_TIMEOUT_MS = 20_000;

const NO_ROWS: Reading[] = [];

/** Counts Realtime topics, so two screens following the same night never share (and close) one channel. */
let nextTopic = 0;

const sameReading = (a: Reading, b: Reading) =>
  a.ts === b.ts && a.temp_c === b.temp_c && a.head_on === b.head_on && a.motion === b.motion;

/** The same rows as before, as far as the charts can tell: same count, same latest reading. */
const sameRows = (a: Reading[], b: Reading[]) =>
  a.length === b.length && (!a.length || sameReading(a[a.length - 1], b[b.length - 1]));

/**
 * `rows` with `incoming` folded in by time, or `rows` itself when nothing changed. Live readings are
 * almost always the latest minute, so that case is a quick look at the end.
 */
function fold(rows: Reading[], incoming: Reading[]): Reading[] {
  let next = rows;
  for (const reading of incoming) {
    const t = Date.parse(reading.ts);
    const last = next[next.length - 1];
    const lastT = last ? Date.parse(last.ts) : -Infinity;
    if (t > lastT) {
      next = [...next, reading];
      continue;
    }
    const i = next.findIndex((r) => Date.parse(r.ts) === t);
    if (i >= 0 && sameReading(next[i], reading)) continue;
    next = i >= 0 ? next.map((r, j) => (j === i ? reading : r)) : [...next, reading];
    if (i < 0) next.sort((a, b) => Date.parse(a.ts) - Date.parse(b.ts));
  }
  return next;
}

/**
 * The pillow's readings between `from` and `to`. A night still in progress (`live`) follows them
 * through Realtime and re-reads every minute as a fallback; a past night reads once. A re-read that
 * fails keeps the rows already shown.
 */
export function useReadings(pillowId: string | null, from: number, to: number, live: boolean) {
  const key = `${pillowId}:${from}:${to}`;
  const [state, setState] = useState<{ key: string; rows: Reading[] } | null>(null);

  useEffect(() => {
    if (!pillowId) return;
    let cancelled = false;
    let reading = false;
    const read = async () => {
      // One read at a time: a slow one is still the latest, so the next tick waits its turn.
      if (reading) return;
      reading = true;
      try {
        let giveUp: ReturnType<typeof setTimeout> | undefined;
        const rows = await Promise.race([
          fetchReadings(pillowId, from, to),
          new Promise<never>((_, reject) => {
            giveUp = setTimeout(() => reject(new Error('Readings timed out')), READ_TIMEOUT_MS);
          }),
        ]).finally(() => clearTimeout(giveUp));
        // Same rows as before: keep the old array, so the charts don't redraw for nothing.
        if (!cancelled) setState((prev) => (prev?.key === key && sameRows(prev.rows, rows) ? prev : { key, rows }));
      } catch {
        // Nothing read yet shows as a night without readings; otherwise what is on screen stays.
        if (!cancelled) setState((prev) => (prev?.key === key ? prev : { key, rows: [] }));
      } finally {
        reading = false;
      }
    };
    void read();
    const id = live ? setInterval(read, LIVE_REFRESH_MS) : undefined;

    // While the night is live, the backend rewrites the current minute every few seconds: gather
    // the changes and fold them into the rows in one go instead of re-reading the whole night.
    const pending: Reading[] = [];
    let flush: ReturnType<typeof setTimeout> | null = null;
    const take = () => {
      flush = null;
      const incoming = pending.splice(0);
      if (cancelled || !incoming.length) return;
      setState((prev) => {
        if (prev?.key !== key) return prev;
        const rows = fold(prev.rows, incoming);
        return rows === prev.rows ? prev : { key, rows };
      });
    };
    const channel = live
      ? supabase
          .channel(`readings:${pillowId}:${nextTopic++}`)
          .on(
            'postgres_changes',
            { event: '*', schema: 'public', table: 'readings', filter: `pillow_id=eq.${pillowId}` },
            (payload) => {
              const row = payload.new as Partial<Reading>;
              if (cancelled || !row.ts) return;
              const t = Date.parse(row.ts);
              if (t < from || t >= to) return;
              pending.push({
                ts: row.ts,
                temp_c: row.temp_c ?? null,
                head_on: row.head_on ?? null,
                motion: row.motion ?? null,
              });
              flush ??= setTimeout(take, LIVE_FLUSH_MS);
            },
          )
          .subscribe()
      : null;
    return () => {
      cancelled = true;
      if (id) clearInterval(id);
      if (flush) clearTimeout(flush);
      if (channel) void supabase.removeChannel(channel);
    };
  }, [pillowId, from, to, live, key]);

  const rows = state?.key === key ? state.rows : null;
  return { rows: rows ?? NO_ROWS, loading: rows === null };
}
