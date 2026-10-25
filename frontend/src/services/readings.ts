/**
 * The pillow's minute-by-minute sensor history (the `readings` table): bedroom temperature,
 * whether a head is on the pillow, and how much the pillow moves. Read straight from Supabase.
 */

import { supabase } from '@/services/supabase/client';

export type Reading = { ts: string; temp_c: number | null; head_on: boolean | null; motion: number | null };

/** Supabase returns at most this many rows per request, so longer windows are read in pages. */
const PAGE_ROWS = 1000;
const MAX_PAGES = 3;

/**
 * Readings in [from, to), oldest first. Throws when the first page can't be read, so a re-read that
 * fails never passes for an empty night; a later page that fails ends the list there.
 */
export async function fetchReadings(pillowId: string, from: number, to: number): Promise<Reading[]> {
  const rows: Reading[] = [];
  for (let page = 0; page < MAX_PAGES; page++) {
    const { data, error } = await supabase
      .from('readings')
      .select('ts, temp_c, head_on, motion')
      .eq('pillow_id', pillowId)
      .gte('ts', new Date(from).toISOString())
      .lt('ts', new Date(to).toISOString())
      .order('ts')
      .range(page * PAGE_ROWS, (page + 1) * PAGE_ROWS - 1);
    if (error || !data) {
      if (page === 0) throw new Error(error?.message ?? 'No readings');
      break;
    }
    rows.push(...(data as Reading[]));
    if (data.length < PAGE_ROWS) break;
  }
  return rows;
}

export type Point = { t: number; v: number | null };

/** Average each `minutes` slot, so a minute-level series draws as a calm line. Empty slots stay null (a gap). */
export function bucket(rows: Reading[], key: 'temp_c' | 'motion', from: number, to: number, minutes: number): Point[] {
  const size = minutes * 60_000;
  const slots = Math.ceil((to - from) / size);
  const sums = new Array<number>(slots).fill(0);
  const counts = new Array<number>(slots).fill(0);
  for (const r of rows) {
    const value = r[key];
    const i = Math.floor((Date.parse(r.ts) - from) / size);
    if (value === null || i < 0 || i >= slots) continue;
    sums[i] += value;
    counts[i] += 1;
  }
  return sums.map((sum, i) => ({ t: from + (i + 0.5) * size, v: counts[i] ? sum / counts[i] : null }));
}

/** Spans of time with a head on the pillow, for the presence strip. */
export function onPillowSpans(rows: Reading[]): { from: number; to: number }[] {
  const spans: { from: number; to: number }[] = [];
  for (const r of rows) {
    const t = Date.parse(r.ts);
    const last = spans[spans.length - 1];
    if (r.head_on) {
      if (last && t - last.to <= 90_000) last.to = t + 60_000;
      else spans.push({ from: t, to: t + 60_000 });
    }
  }
  return spans;
}

export type NightClimate = {
  /** Temperature when she lay down, and when she got up (or the latest). */
  start: number;
  end: number;
  coldest: { t: number; v: number };
  warmest: { t: number; v: number };
  /** Minutes with a head on the pillow. */
  onPillowMin: number;
};

/** The numbers the stat tiles show; null when there are no temperature readings. */
export function nightClimate(rows: Reading[]): NightClimate | null {
  const temps = rows.filter((r) => r.temp_c !== null).map((r) => ({ t: Date.parse(r.ts), v: r.temp_c as number }));
  if (!temps.length) return null;
  const onPillow = rows.filter((r) => r.head_on);
  const firstIn = onPillow.length ? Date.parse(onPillow[0].ts) : temps[0].t;
  const lastIn = onPillow.length ? Date.parse(onPillow[onPillow.length - 1].ts) : temps[temps.length - 1].t;
  const near = (t: number) => temps.reduce((best, p) => (Math.abs(p.t - t) < Math.abs(best.t - t) ? p : best));
  return {
    start: near(firstIn).v,
    end: near(lastIn).v,
    coldest: temps.reduce((a, b) => (b.v < a.v ? b : a)),
    warmest: temps.reduce((a, b) => (b.v > a.v ? b : a)),
    onPillowMin: onPillow.length,
  };
}

/** "+1.2°C" / "-2.4°C" / "No change". */
export function signedDegrees(delta: number): string {
  const rounded = Math.round(delta * 10) / 10;
  if (rounded === 0) return 'No change';
  return `${rounded > 0 ? '+' : '−'}${Math.abs(rounded).toFixed(1)}°C`;
}
