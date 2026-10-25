import {
  createContext,
  type PropsWithChildren,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
} from 'react';
import { AppState } from 'react-native';

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

/**
 * Everything read for the pillow except its live state row, which changes with every heartbeat and
 * so has its own hook, `usePillowState`: screens that don't show it never re-render for it.
 */
export type PillowData = {
  resident: Resident | null;
  events: EventRow[];
  incidents: IncidentRow[];
  reminders: Reminder[];
  occurrences: Occurrence[];
  loading: boolean;
  /** Set when the pillow could not be read; what was read before stays on screen. */
  error: string | null;
  /** Read everything again. Never rejects; resolves once the read (and any asked for meanwhile) lands. */
  refresh: () => Promise<void>;
};

const DAY_MS = 24 * 60 * 60 * 1000;
/** How far back events and incidents are read: the month chart plus the night in progress. */
const HISTORY_DAYS = MONTH_NIGHTS + 2;
const HISTORY_MS = HISTORY_DAYS * DAY_MS;

/** How long to gather a burst of Realtime changes before reading again. */
const REFRESH_DEBOUNCE_MS = 1500;
/** How long one part of a read may take before it counts as failed, so a dead network never spins forever. */
const READ_TIMEOUT_MS = 15_000;
/**
 * The pillow posts its state about twice a second, but only `last_seen_at` moves. Screens get the
 * new time at most this often (the latest always lands within it); a new night state shows at once.
 */
const HEARTBEAT_EVERY_MS = 10_000;

const FAILED = "Couldn't reach the pillow's records. Pull down to try again.";

type Rows = Omit<PillowData, 'refresh'>;

const EMPTY: Rows = {
  resident: null,
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

/** `next` where it was read, `prev` where that part failed (undefined), each kept if unchanged. */
function merge<T>(prev: T, next: T | undefined): T {
  return next === undefined ? prev : keep(prev, next);
}

/** What `read` resolves to, or undefined if it failed or took too long. */
function settle<T>(read: PromiseLike<T>): Promise<T | undefined> {
  return new Promise((resolve) => {
    const timer = setTimeout(() => resolve(undefined), READ_TIMEOUT_MS);
    Promise.resolve(read).then(
      (value) => {
        clearTimeout(timer);
        resolve(value);
      },
      () => {
        clearTimeout(timer);
        resolve(undefined);
      },
    );
  });
}

/** A Supabase read's rows, or undefined when it failed. */
function rowsOf<T>(read: PromiseLike<{ data: unknown; error: unknown }>): Promise<T | undefined> {
  return settle(read).then((r) => (r && !r.error ? (r.data as T) : undefined));
}

/**
 * The pillow's events for the month, read straight from Supabase (only its household may read
 * them). If that fails, fall back to the backend's last night rather than show nothing; undefined
 * when neither answers.
 */
async function readEvents(pillowId: string): Promise<EventRow[] | undefined> {
  const rows = await rowsOf<EventRow[]>(
    supabase
      .from('events')
      .select('event_type, device_ts, data')
      .eq('pillow_id', pillowId)
      .gte('device_ts', new Date(Date.now() - HISTORY_MS).toISOString())
      .order('device_ts'),
  );
  if (rows) return rows;
  return settle(api<{ events: EventRow[] }>(`/pillows/${pillowId}/night`)).then((n) => n?.events);
}

/** One read of everything; each part is undefined when it failed, so the screen keeps what it had. */
async function readPillow(pillowId: string) {
  const since = new Date(Date.now() - HISTORY_MS).toISOString();
  const [pillow, state, events, incidents, reminders, occurrences] = await Promise.all([
    rowsOf<{ residents: unknown } | null>(
      supabase.from('pillows').select('residents(*)').eq('id', pillowId).maybeSingle(),
    ),
    rowsOf<PillowStateRow | null>(
      supabase.from('pillow_state').select('night_state, state_since, last_seen_at').eq('pillow_id', pillowId).maybeSingle(),
    ),
    readEvents(pillowId),
    rowsOf<IncidentRow[]>(
      supabase
        .from('incidents')
        .select('id, kind, status, opened_at, acked_at, acked_by, resolved_at, resolved_reason, summary')
        .eq('pillow_id', pillowId)
        .gte('opened_at', since)
        .order('opened_at', { ascending: false }),
    ),
    settle(api<Reminder[]>(`/pillows/${pillowId}/reminders`)),
    settle(api<Occurrence[]>(`/pillows/${pillowId}/reminders/today`)),
  ]);
  const resident = pillow === undefined ? undefined : ((pillow?.residents ?? null) as Resident | null);
  // Reminders have their own screen and error; a pillow without them simply shows none.
  const failed = !resident || state === undefined || events === undefined || incidents === undefined;
  return { resident, state, events, incidents, reminders, occurrences, failed };
}

const noRefresh = () => Promise.resolve();

/** Counts Realtime topics, so no two channels this app opens share one. */
let nextTopic = 0;

const PillowContext = createContext<PillowData>({ ...EMPTY, refresh: noRefresh });
const PillowStateContext = createContext<PillowStateRow | null>(null);

/**
 * Loads everything the app shows for one pillow, once, for every screen under it, and keeps it
 * live: the state and incidents through Supabase Realtime, and events and today's reminders from
 * the backend. A live pillow posts every second or so, so a heartbeat only updates the state row
 * (in its own context); a change of night state or an incident re-reads the rest, gathered into
 * one read per burst. One read runs at a time: asking while one runs reads once more after it.
 */
export function PillowProvider({ pillowId, children }: PropsWithChildren<{ pillowId: string | null }>) {
  const [data, setData] = useState(EMPTY);
  const [live, setLive] = useState<PillowStateRow | null>(null);
  // The current pillow's read, so `refresh` itself never changes.
  const refreshRef = useRef<() => Promise<void>>(noRefresh);
  // Switching to another person's pillow drops the last one's data at once, so nothing of theirs shows.
  const [shown, setShown] = useState(pillowId);
  if (shown !== pillowId) {
    setShown(pillowId);
    setData(EMPTY);
    setLive(null);
  }

  useEffect(() => {
    if (!pillowId) return;
    // Everything below belongs to this pillow; once it is switched away, late answers are dropped.
    let stopped = false;
    let running: Promise<void> | null = null;
    let again = false;
    let soon: ReturnType<typeof setTimeout> | null = null;
    // The state row screens see, and a newer heartbeat waiting for its turn.
    let published: PillowStateRow | null = null;
    let waiting: PillowStateRow | null = null;
    let beat: ReturnType<typeof setTimeout> | null = null;

    const publish = (row: PillowStateRow | null) => {
      if (beat) clearTimeout(beat);
      beat = null;
      waiting = null;
      published = row;
      setLive((prev) => keep(prev, row));
    };

    /** Show a state row: a new state at once, a heartbeat at most every HEARTBEAT_EVERY_MS. */
    const showState = (row: PillowStateRow) => {
      if (
        !published ||
        published.night_state !== row.night_state ||
        published.state_since !== row.state_since ||
        Date.parse(row.last_seen_at) - Date.parse(published.last_seen_at) >= HEARTBEAT_EVERY_MS
      ) {
        publish(row);
        return;
      }
      waiting = row;
      beat ??= setTimeout(() => {
        beat = null;
        if (waiting && !stopped) publish(waiting);
      }, HEARTBEAT_EVERY_MS);
    };

    const readOnce = async () => {
      const next = await readPillow(pillowId);
      if (stopped) return;
      // A heartbeat that came in while reading is newer than the row read; keep it.
      const latest = waiting ?? published;
      if (next.state === null && !latest) publish(null);
      else if (next.state && (!latest || Date.parse(next.state.last_seen_at) >= Date.parse(latest.last_seen_at))) {
        showState(next.state);
      }
      setData((prev) => {
        const merged: Rows = {
          resident: merge(prev.resident, next.resident),
          events: merge(prev.events, next.events),
          incidents: merge(prev.incidents, next.incidents),
          reminders: merge(prev.reminders, next.reminders),
          occurrences: merge(prev.occurrences, next.occurrences),
          loading: false,
          error: next.failed ? FAILED : null,
        };
        const same = (Object.keys(merged) as (keyof Rows)[]).every((k) => merged[k] === prev[k]);
        return same ? prev : merged;
      });
    };

    const refresh = (): Promise<void> => {
      if (stopped) return Promise.resolve();
      if (running) {
        again = true;
        return running;
      }
      running = (async () => {
        try {
          do {
            again = false;
            await readOnce();
          } while (again && !stopped);
        } finally {
          running = null;
        }
      })();
      return running;
    };

    const refreshSoon = () => {
      if (soon) clearTimeout(soon);
      soon = setTimeout(() => {
        soon = null;
        void refresh();
      }, REFRESH_DEBOUNCE_MS);
    };

    const onState = (payload: { new: Partial<PillowStateRow> }) => {
      const row = payload.new;
      if (!row || !row.night_state || !row.last_seen_at) return refreshSoon();
      const before = (waiting ?? published)?.night_state;
      const moved = before !== undefined && before !== row.night_state;
      showState({
        night_state: row.night_state,
        state_since: row.state_since ?? '',
        last_seen_at: row.last_seen_at,
      });
      // A new night state comes with new events (lay down, got up ...), so read those too.
      if (moved) refreshSoon();
    };

    refreshRef.current = refresh;
    const channel = supabase
      // A topic of its own, so a provider remounting before the last channel has gone never shares it.
      .channel(`pillow-${pillowId}-${nextTopic++}`)
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
        if (status === 'SUBSCRIBED' || status === 'CHANNEL_ERROR' || status === 'TIMED_OUT') void refresh();
      });
    return () => {
      stopped = true;
      if (refreshRef.current === refresh) refreshRef.current = noRefresh;
      if (soon) clearTimeout(soon);
      if (beat) clearTimeout(beat);
      void supabase.removeChannel(channel);
    };
  }, [pillowId]);

  const refresh = useCallback(() => refreshRef.current(), []);
  const value = useMemo(() => ({ ...data, refresh }), [data, refresh]);
  return (
    <PillowContext.Provider value={value}>
      <PillowStateContext.Provider value={live}>{children}</PillowStateContext.Provider>
    </PillowContext.Provider>
  );
}

/** The linked pillow's data, from the nearest PillowProvider. */
export function usePillow(): PillowData {
  return useContext(PillowContext);
}

/**
 * The pillow's live state row (night state and when it was last heard from), or null before it is
 * read. Changes far more often than the rest, so only the parts of a screen that show it should ask.
 */
export function usePillowState(): PillowStateRow | null {
  return useContext(PillowStateContext);
}

type Clock = { now: number; listeners: Set<() => void>; stop: (() => void) | null };

/** One clock per interval, shared by every screen, so they all move on together in one render. */
const clocks = new Map<number, Clock>();

function clockFor(ms: number): Clock {
  let clock = clocks.get(ms);
  if (!clock) {
    clock = { now: Date.now(), listeners: new Set(), stop: null };
    clocks.set(ms, clock);
  }
  return clock;
}

function tick(clock: Clock) {
  clock.now = Date.now();
  clock.listeners.forEach((l) => l());
}

/** Starts the `ms` clock with its first listener, and stops it with its last. */
function subscribeClock(ms: number, listener: () => void): () => void {
  const clock = clockFor(ms);
  clock.listeners.add(listener);
  if (!clock.stop) {
    const id = setInterval(() => tick(clock), ms);
    // Timers pause while the app is away, so coming back catches up at once.
    const sub = AppState.addEventListener('change', (state) => {
      if (state === 'active') tick(clock);
    });
    clock.stop = () => {
      clearInterval(id);
      sub.remove();
    };
  }
  return () => {
    clock.listeners.delete(listener);
    if (!clock.listeners.size && clock.stop) {
      clock.stop();
      clock.stop = null;
    }
  };
}

/** The `ms` clock's time; one nobody has watched for a while catches up first. */
function readClock(ms: number): number {
  const clock = clockFor(ms);
  if (!clock.stop && Date.now() - clock.now >= ms) clock.now = Date.now();
  return clock.now;
}

/** A clock that ticks every `ms`, so "asleep for" and "offline" stay true without new data. */
export function useNow(ms = 30_000): number {
  const subscribe = useCallback((listener: () => void) => subscribeClock(ms, listener), [ms]);
  const read = useCallback(() => readClock(ms), [ms]);
  return useSyncExternalStore(subscribe, read, read);
}
