import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AppState } from 'react-native';

import type { Occurrence } from '@/hooks/usePillow';
import { ApiError } from '@/services/api';
import { CALENDAR_MAX_DAYS, listReminders, readCalendar, type Reminder } from '@/services/reminders';
import { addDays, daysBetween, expandCalendar, normaliseReminder, type Slot, toSlot } from '@/services/schedule';

/** How long a move or skip waits, undoable, before it goes to the pillow. */
export const UNDO_MS = 7000;

/**
 * A change shown at once but sent only once the undo window closes, so undoing it costs nothing
 * (sending and reverting a move would make her agree twice).
 */
export type Staged = {
  /** "Moved to Thu 2:15 pm." */
  message: string;
  /** A second line, for consent: "Margaret will be asked again." */
  detail?: string;
  /** How the calendar looks with the change made. */
  preview: (slots: Slot[]) => Slot[];
  commit: () => Promise<unknown>;
};

export type RemindersData = {
  reminders: Reminder[];
  slots: Slot[];
  loading: boolean;
  /** Set when the reminders could not be read at all, in words. */
  error: string | null;
  refresh: () => Promise<void>;
  /** The change waiting out its undo window, if any. */
  staged: Staged | null;
  stage: (change: Staged) => void;
  undo: () => void;
  /** Set when a staged change failed to send. */
  sendError: string | null;
  clearSendError: () => void;
};

/** Why the reminders can't be shown, in words the family can act on. */
function readError(e: unknown): string {
  if (e instanceof ApiError && (e.status === 404 || e.status === 405)) {
    return "This pillow can't show reminders yet. They arrive with its next update.";
  }
  return "Couldn't reach the pillow's reminders. Check your connection and try again.";
}

/** One calendar read, or two when the range is longer than the backend allows. */
async function readRange(pillowId: string, start: string, end: string) {
  if (daysBetween(start, end) < CALENDAR_MAX_DAYS) return readCalendar(pillowId, start, end);
  const middle = addDays(start, CALENDAR_MAX_DAYS - 1);
  const [a, b] = await Promise.all([
    readCalendar(pillowId, start, middle),
    readCalendar(pillowId, addDays(middle, 1), end),
  ]);
  return [...a, ...b];
}

/**
 * The pillow's reminders and when they play from `start` to `end` on her clock. Reads GET
 * /calendar; on a backend without it, works the days out on the phone from the reminders
 * themselves. Moves and skips are staged: shown straight away, sent after UNDO_MS, or at once if the
 * screen closes or the app goes to the background.
 */
export function useReminders(
  pillowId: string | null,
  start: string,
  end: string,
  tz: string,
  today: { date: string; occurrences: Occurrence[] },
): RemindersData {
  const [reminders, setReminders] = useState<Reminder[]>([]);
  const [slots, setSlots] = useState<Slot[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [staged, setStaged] = useState<Staged | null>(null);
  const [sendError, setSendError] = useState<string | null>(null);
  const stagedRef = useRef<Staged | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  // The latest read, so a slow answer for an old week never replaces a newer one.
  const readId = useRef(0);

  const todayStatus = useMemo(
    () => new Map(today.occurrences.map((o) => [o.reminder_id, o.status])),
    [today.occurrences],
  );

  /** Reads the reminders and their days; sets nothing, so the effect below can apply it when it lands. */
  const read = useCallback(async (): Promise<{ list: Reminder[]; days: Slot[] } | { error: string }> => {
    try {
      const list = (await listReminders(pillowId!)).map(normaliseReminder);
      const byId = new Map(list.map((r) => [r.id, r]));
      const days = await readRange(pillowId!, start, end).then(
        (entries) => entries.map((e) => toSlot(e, tz, byId.get(e.reminder_id)?.time_of_day)),
        (e: unknown) => {
          if (e instanceof ApiError && (e.status === 404 || e.status === 405)) {
            return expandCalendar(list, start, end, { date: today.date, status: todayStatus });
          }
          throw e;
        },
      );
      return { list, days };
    } catch (e) {
      return { error: readError(e) };
    }
  }, [pillowId, start, end, tz, today.date, todayStatus]);

  /** Shows a read, unless a newer one has started since. */
  const apply = useCallback((id: number, result: Awaited<ReturnType<typeof read>>) => {
    if (id !== readId.current) return;
    if ('error' in result) setError(result.error);
    else {
      setReminders(result.list);
      setSlots(result.days);
      setError(null);
    }
    setLoading(false);
  }, []);

  const refresh = useCallback(async () => {
    if (!pillowId) return;
    const id = ++readId.current;
    apply(id, await read());
  }, [pillowId, read, apply]);

  useEffect(() => {
    if (!pillowId) return;
    const id = ++readId.current;
    read().then((result) => apply(id, result));
  }, [pillowId, read, apply]);

  /** Sends the staged change now (its window closed, or another change replaces it). */
  const send = useCallback(async () => {
    const change = stagedRef.current;
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
    stagedRef.current = null;
    if (!change) return;
    // Keep the change on screen while it goes, so nothing jumps back until the fresh read lands.
    setSlots((current) => change.preview(current));
    setStaged(null);
    try {
      await change.commit();
    } catch {
      setSendError("Couldn't send that change to the pillow. Nothing was changed, so try again.");
    }
    await refresh();
  }, [refresh]);

  const stage = useCallback(
    (change: Staged) => {
      if (stagedRef.current) send();
      stagedRef.current = change;
      setStaged(change);
      setSendError(null);
      timer.current = setTimeout(send, UNDO_MS);
    },
    [send],
  );

  const undo = useCallback(() => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
    stagedRef.current = null;
    setStaged(null);
  }, []);

  // Leaving the screen, or putting the app away, sends what is waiting rather than dropping it.
  const sendRef = useRef(send);
  useEffect(() => {
    sendRef.current = send;
  }, [send]);
  useEffect(() => {
    const sub = AppState.addEventListener('change', (state) => {
      if (state === 'background') void sendRef.current();
    });
    return () => {
      sub.remove();
      void sendRef.current();
    };
  }, []);

  const shown = useMemo(() => (staged ? staged.preview(slots) : slots), [staged, slots]);

  return {
    reminders,
    slots: shown,
    loading,
    error,
    refresh,
    staged,
    stage,
    undo,
    sendError,
    clearSendError: useCallback(() => setSendError(null), []),
  };
}
