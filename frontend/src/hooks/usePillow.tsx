import {
  createContext,
  type PropsWithChildren,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';

import { MONTH_NIGHTS } from '@/constants/pillow';
import { api } from '@/services/api';
import type { EventRow, IncidentRow, PillowStateRow } from '@/services/night';
import type { Reminder } from '@/services/reminders';
import { supabase } from '@/services/supabase/client';

export type Resident = {
  id: string;
  preferred_name: string;
  timezone: string;
  voice_id: string;
  quiet_start: string;
  quiet_end: string;
  checkin_timeout_min: number;
  monitoring_paused: boolean;
};

/** One of today's reminders that has fallen due, and how it went. */
export type Occurrence = {
  reminder_id: number;
  due_at: string;
  status: 'waiting' | 'due' | 'announced' | 'done' | 'missed';
};

export type { Reminder };

export type PillowData = {
  resident: Resident | null;
  state: PillowStateRow | null;
  events: EventRow[];
  incidents: IncidentRow[];
  reminders: Reminder[];
  occurrences: Occurrence[];
  loading: boolean;
  /** Set when the pillow could not be read at all. */
  error: string | null;
  refresh: () => Promise<void>;
};

const DAY_MS = 24 * 60 * 60 * 1000;
/** How far back events and incidents are read: the month chart plus the night in progress. */
const HISTORY_DAYS = MONTH_NIGHTS + 2;
const HISTORY_MS = HISTORY_DAYS * DAY_MS;

/**
 * The pillow's events for the week, read straight from Supabase (only its household may read
 * them). If that fails, fall back to the backend's last night rather than show nothing.
 */
async function readEvents(pillowId: string): Promise<EventRow[]> {
  const { data, error } = await supabase
    .from('events')
    .select('event_type, device_ts, data')
    .eq('pillow_id', pillowId)
    .gte('device_ts', new Date(Date.now() - HISTORY_MS).toISOString())
    .order('device_ts');
  if (!error && data) return data as EventRow[];
  return api<{ events: EventRow[] }>(`/pillows/${pillowId}/night`).then(
    (n) => n.events,
    () => [],
  );
}

/** How long to gather a burst of Realtime changes before reading again. */
const REFRESH_DEBOUNCE_MS = 1500;

const EMPTY: Omit<PillowData, 'refresh'> = {
  resident: null,
  state: null,
  events: [],
  incidents: [],
  reminders: [],
  occurrences: [],
  loading: true,
  error: null,
};

/** `next`, or `prev` itself when nothing in it changed, so screens skip re-rendering what they already show. */
function keep<T>(prev: T, next: T): T {
  return JSON.stringify(prev) === JSON.stringify(next) ? prev : next;
}

const PillowContext = createContext<PillowData>({ ...EMPTY, refresh: async () => {} });

/**
 * Loads everything the app shows for one pillow, once, for every screen under it, and keeps it
 * live: the state and incidents through Supabase Realtime, and events and today's reminders from
 * the backend. A live pillow posts every few seconds, so a heartbeat only updates the state row;
 * a change of night state or an incident re-reads the rest, gathered into one read per burst.
 */
export function PillowProvider({ pillowId, children }: PropsWithChildren<{ pillowId: string | null }>) {
  const [data, setData] = useState(EMPTY);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Switching to another person's pillow drops the last one's data at once, so nothing of theirs shows.
  const [shown, setShown] = useState(pillowId);
  if (shown !== pillowId) {
    setShown(pillowId);
    setData(EMPTY);
  }

  const refresh = useCallback(async () => {
    if (!pillowId) return;
    const since = new Date(Date.now() - HISTORY_MS).toISOString();
    const [pillow, state, events, incidents, reminders, occurrences] = await Promise.all([
      supabase.from('pillows').select('residents(*)').eq('id', pillowId).maybeSingle(),
      supabase
        .from('pillow_state')
        .select('night_state, state_since, last_seen_at')
        .eq('pillow_id', pillowId)
        .maybeSingle(),
      readEvents(pillowId),
      supabase
        .from('incidents')
        .select('id, kind, status, opened_at, acked_at, resolved_at, summary')
        .eq('pillow_id', pillowId)
        .gte('opened_at', since)
        .order('opened_at', { ascending: false }),
      api<Reminder[]>(`/pillows/${pillowId}/reminders`).catch(() => [] as Reminder[]),
      api<Occurrence[]>(`/pillows/${pillowId}/reminders/today`).catch(() => [] as Occurrence[]),
    ]);
    const resident = (pillow.data?.residents ?? null) as unknown as Resident | null;
    setData((prev) => ({
      resident: keep(prev.resident, resident),
      state: keep(prev.state, (state.data as PillowStateRow | null) ?? null),
      events: keep(prev.events, events),
      incidents: keep(prev.incidents, (incidents.data as IncidentRow[] | null) ?? []),
      reminders: keep(prev.reminders, reminders),
      occurrences: keep(prev.occurrences, occurrences),
      loading: false,
      error: pillow.error || !resident ? "Couldn't reach the pillow's records. Pull down to try again." : null,
    }));
  }, [pillowId]);

  const refreshSoon = useCallback(() => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(refresh, REFRESH_DEBOUNCE_MS);
  }, [refresh]);

  useEffect(() => {
    if (!pillowId) return;
    const onState = (payload: { new: Partial<PillowStateRow> }) => {
      const row = payload.new;
      if (!row || !('night_state' in row)) return refreshSoon();
      let moved = false;
      setData((prev) => {
        moved = prev.state?.night_state !== row.night_state;
        const next = {
          night_state: row.night_state,
          state_since: row.state_since,
          last_seen_at: row.last_seen_at,
        } as PillowStateRow;
        return { ...prev, state: keep(prev.state, next) };
      });
      // A new night state comes with new events (lay down, got up ...), so read those too.
      if (moved) refreshSoon();
    };
    const channel = supabase
      .channel(`pillow-${pillowId}`)
      .on(
        'postgres_changes',
        { event: '*', schema: 'public', table: 'pillow_state', filter: `pillow_id=eq.${pillowId}` },
        onState,
      )
      .on(
        'postgres_changes',
        { event: '*', schema: 'public', table: 'incidents', filter: `pillow_id=eq.${pillowId}` },
        refreshSoon,
      )
      .on('postgres_changes', { event: '*', schema: 'public', table: 'reminder_occurrences' }, refreshSoon)
      // Read once the channel is listening (so no change slips between the read and the
      // subscription), or straight away if Realtime can't connect.
      .subscribe((status) => {
        if (status === 'SUBSCRIBED' || status === 'CHANNEL_ERROR' || status === 'TIMED_OUT') refresh();
      });
    return () => {
      if (timer.current) clearTimeout(timer.current);
      supabase.removeChannel(channel);
    };
  }, [pillowId, refresh, refreshSoon]);

  const value = useMemo(() => ({ ...data, refresh }), [data, refresh]);
  return <PillowContext.Provider value={value}>{children}</PillowContext.Provider>;
}

/** The linked pillow's data, from the nearest PillowProvider. */
export function usePillow(): PillowData {
  return useContext(PillowContext);
}

/** A clock that ticks every `ms`, so "asleep for" and "offline" stay true without new data. */
export function useNow(ms = 30_000): number {
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), ms);
    return () => clearInterval(id);
  }, [ms]);
  return now;
}
