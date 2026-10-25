/**
 * Turns the pillow's raw rows (state, events, incidents) into what the Tonight screen says. Plain
 * functions with no I/O, all in the resident's timezone, so the times match her clock, not the phone's.
 */

import {
  NIGHT_ENDS_HOUR,
  NIGHT_STARTS_HOUR,
  OFFLINE_AFTER_MS,
  RIBBON_HOURS,
  RIBBON_START_HOUR,
} from '@/constants/pillow';
import type { PillowState } from '@/constants/status';
import type { RibbonSegment } from '@/components/NightRibbon';
import type { Occurrence, Reminder } from '@/hooks/usePillow';
import type { PillowPing } from '@/services/ping';

export type NightState = 'awake' | 'in_bed' | 'up' | 'check_in' | 'escalating';

export type PillowStateRow = {
  night_state: NightState;
  state_since: string;
  last_seen_at: string;
};

export type EventRow = {
  event_type: string;
  device_ts: string;
  data: Record<string, unknown> | null;
};

export type IncidentRow = {
  id: number;
  kind: string;
  status: 'open' | 'acknowledged' | 'resolved' | 'cancelled';
  opened_at: string;
  acked_at: string | null;
  /** The contact who pressed "I'm on it". */
  acked_by: string | null;
  resolved_at: string | null;
  /** Why it ended: she said she's fine, she's back in bed, or it was cleared (the simulator). */
  resolved_reason: 'fine' | 'back_in_bed' | 'cleared' | null;
  summary: string | null;
};

const HOUR_MS = 60 * 60 * 1000;
const DAY_MS = 24 * HOUR_MS;

// ---------- time in her timezone ----------

const formatters = new Map<string, Intl.DateTimeFormat>();

/**
 * One formatter per kind and timezone, made once: building an Intl.DateTimeFormat is slow on the
 * phone, and a month of nights asks for hundreds of dates.
 */
export function formatter(
  kind: string,
  tz: string,
  options: Intl.DateTimeFormatOptions,
  locale = 'en-US',
): Intl.DateTimeFormat {
  const key = `${kind}|${locale}|${tz}`;
  let f = formatters.get(key);
  if (!f) {
    f = new Intl.DateTimeFormat(locale, { timeZone: tz, ...options });
    formatters.set(key, f);
  }
  return f;
}

/** Year, month, day, hour and minute of `ms` on the resident's clock. */
function partsIn(ms: number, tz: string) {
  const parts = formatter('parts', tz, {
    hourCycle: 'h23',
    year: 'numeric',
    month: 'numeric',
    day: 'numeric',
    hour: 'numeric',
    minute: 'numeric',
  }).formatToParts(new Date(ms));
  const get = (type: string) => Number(parts.find((p) => p.type === type)?.value);
  return {
    year: get('year'),
    month: get('month'),
    day: get('day'),
    hour: get('hour'),
    minute: get('minute'),
  };
}

/** The instant when her clock reads `hour`:00 on the day `dayMs` falls on, shifted by `addDays`. */
function atHour(dayMs: number, hour: number, tz: string, addDays = 0): number {
  const p = partsIn(dayMs, tz);
  const wall = Date.UTC(p.year, p.month - 1, p.day + addDays, hour);
  // Correct the guess by her UTC offset at that moment (twice, to settle across a DST change).
  let guess = wall;
  for (let i = 0; i < 2; i++) {
    const g = partsIn(guess, tz);
    guess += wall - Date.UTC(g.year, g.month - 1, g.day, g.hour, g.minute);
  }
  return guess;
}

/** "3:12 am", on her clock. */
export function clockTime(iso: string | number, tz: string): string {
  return formatter('clock', tz, { hour: 'numeric', minute: '2-digit' })
    .format(new Date(iso))
    .replace(' AM', ' am')
    .replace(' PM', ' pm');
}

/** "Thursday", on her clock. */
function weekday(ms: number, tz: string): string {
  return formatter('weekday', tz, { weekday: 'long' }).format(new Date(ms));
}

/** "3h 18m" or "42m". */
export function duration(ms: number): string {
  const minutes = Math.max(0, Math.round(ms / 60000));
  const h = Math.floor(minutes / 60);
  return h ? `${h}h ${minutes % 60}m` : `${minutes}m`;
}

// ---------- which night ----------

export type NightWindow = {
  /** 6 pm on the evening the night starts. */
  start: number;
  /** Noon the next day. */
  end: number;
  /** 10 pm, where the ribbon starts. */
  ribbonStart: number;
  /** True once the night is over (it's afternoon), so the screen talks about "last night". */
  over: boolean;
};

/** The night in progress, or the one that just ended when it's between noon and 6 pm. */
export function currentNight(now: number, tz: string): NightWindow {
  const hour = partsIn(now, tz).hour;
  const evening = hour >= NIGHT_STARTS_HOUR ? now : now - DAY_MS;
  return {
    start: atHour(evening, NIGHT_STARTS_HOUR, tz),
    end: atHour(evening, NIGHT_ENDS_HOUR, tz, 1),
    ribbonStart: atHour(evening, RIBBON_START_HOUR, tz),
    over: hour >= NIGHT_ENDS_HOUR && hour < NIGHT_STARTS_HOUR,
  };
}

/**
 * The night Tonight leads with: the one in progress once she has lain down, else the one that just
 * ended. From 6 pm until bedtime that keeps last night (yesterday evening to this morning) on screen
 * instead of an empty new night.
 */
export function latestNight(all: EventRow[], now: number, tz: string): NightWindow {
  const current = currentNight(now, tz);
  if (current.over || all.some((e) => e.event_type === 'lay_down' && Date.parse(e.device_ts) >= current.start)) {
    return current;
  }
  return pastNights(current, 1, tz)[0];
}

/** The `count` nights before `night`, newest first. */
export function pastNights(night: NightWindow, count: number, tz: string): NightWindow[] {
  return Array.from({ length: count }, (_, i) => {
    const evening = night.start - (i + 1) * DAY_MS + HOUR_MS; // an hour in, clear of DST edges
    return {
      start: atHour(evening, NIGHT_STARTS_HOUR, tz),
      end: atHour(evening, NIGHT_ENDS_HOUR, tz, 1),
      ribbonStart: atHour(evening, RIBBON_START_HOUR, tz),
      over: true,
    };
  });
}

type Timed = { rows: EventRow[]; times: number[] };

/** Each list of events sorted once, with its times parsed, for as long as that list is on screen. */
const timed = new WeakMap<EventRow[], Timed>();

function timedOf(all: EventRow[]): Timed {
  let t = timed.get(all);
  if (!t) {
    const rows = all
      .map((e) => ({ e, t: Date.parse(e.device_ts) }))
      .sort((a, b) => a.t - b.t);
    t = { rows: rows.map((r) => r.e), times: rows.map((r) => r.t) };
    timed.set(all, t);
  }
  return t;
}

/** The first index whose time is at or after `t`. */
function firstAt(times: number[], t: number): number {
  let lo = 0;
  let hi = times.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (times[mid] < t) lo = mid + 1;
    else hi = mid;
  }
  return lo;
}

/** The night's events, oldest first. */
const within = (all: EventRow[], w: NightWindow) => {
  const { rows, times } = timedOf(all);
  return rows.slice(firstAt(times, w.start), firstAt(times, w.end));
};

// ---------- the status headline ----------

/**
 * The five app states from the backend's night_state; a silent pillow is offline, not "fine". `live`
 * is the alert in progress: once someone pressed "I'm on it" the pillow stops calling round but stays
 * escalating until she's back in bed or says she's fine, so the app shows her as up, not alarmed.
 */
export function appState(
  row: PillowStateRow | null,
  events: EventRow[],
  now: number,
  live: IncidentRow | null = null,
): PillowState {
  if (!row || now - Date.parse(row.last_seen_at) > OFFLINE_AFTER_MS) return 'offline';
  switch (row.night_state) {
    case 'escalating':
      return live?.status === 'acknowledged' ? 'up' : 'alert';
    case 'up':
    case 'check_in':
    case 'awake':
      return 'up';
    case 'in_bed': {
      const last = [...events].reverse().find((e) => e.event_type === 'restless' || e.event_type === 'settled');
      return last?.event_type === 'restless' ? 'restless' : 'asleep';
    }
  }
}

/**
 * The line under the headline: when this state began, in plain words. Offline, `ping` (the app's
 * own check every few seconds) says which part of the pillow isn't answering. Up after "I'm on it",
 * `onIt` says who is ("You're on it.").
 */
export function stateDetail(
  state: PillowState,
  row: PillowStateRow | null,
  events: EventRow[],
  tz: string,
  now: number,
  ping: PillowPing | null = null,
  onIt = 'Someone is on it.',
): string {
  if (!row) return 'Waiting for the pillow to say hello.';
  const since = clockTime(row.state_since, tz);
  const latest = (type: string) => [...events].reverse().find((e) => e.event_type === type);
  const upSince = () => clockTime(latest('bed_exit')?.device_ts ?? row.state_since, tz);
  switch (state) {
    case 'offline': {
      const heard = `Last heard from ${duration(now - Date.parse(row.last_seen_at))} ago, at ${clockTime(row.last_seen_at, tz)}.`;
      if (ping?.active) return `${heard}\nIt's answering again. Catching up now.`;
      if (ping?.node_alive) return `${heard}\nThe pillow is on, but its bedside speaker isn't answering. Check it's plugged in.`;
      return `${heard}\nCheck it's plugged in and the Wi-Fi is on. Checking again every few seconds.`;
    }
    case 'asleep': {
      const asleep = latest('asleep');
      const lay = latest('lay_down');
      const parts = [`In bed since ${clockTime(lay?.device_ts ?? row.state_since, tz)}.`];
      if (asleep) parts.push(`Settled since ${clockTime(asleep.device_ts, tz)}.`);
      return parts.join('\n');
    }
    case 'restless':
      return `In bed since ${since}, moving about.`;
    case 'up':
      if (row.night_state === 'escalating') return `Up since ${upSince()}. ${onIt}`;
      if (row.night_state === 'check_in') return `Up since ${since}. The pillow is checking in.`;
      if (row.night_state === 'awake') {
        const gotUp = latest('got_up');
        return gotUp ? `Up for the day since ${clockTime(gotUp.device_ts, tz)}.` : `Up since ${since}.`;
      }
      return `Up since ${since}.`;
    case 'alert':
      return `Up since ${upSince()}. Family are being told.`;
  }
}

// ---------- the ribbon and the stats ----------

/** Ribbon bars for one night: in bed, restless, up, and up with family alerted. */
export function ribbonSegments(all: EventRow[], w: NightWindow, now: number): RibbonSegment[] {
  const hours = (iso: string | number) =>
    (Number(typeof iso === 'string' ? Date.parse(iso) : iso) - w.ribbonStart) / HOUR_MS;
  const end = Math.min(now, w.end);
  const segments: RibbonSegment[] = [];
  let bedFrom: number | null = null;
  let upFrom: number | null = null;
  let restlessFrom: number | null = null;
  let alerted = false;
  const close = (kind: RibbonSegment['kind'], from: number | null, to: number) => {
    if (from !== null && to > from) segments.push({ kind, from, to });
  };
  for (const e of within(all, w)) {
    const t = hours(e.device_ts);
    switch (e.event_type) {
      case 'lay_down':
      case 'bed_return':
        if (upFrom !== null) close(alerted ? 'alert' : 'up', upFrom, t);
        upFrom = null;
        alerted = false;
        bedFrom = t;
        break;
      case 'restless':
        restlessFrom = t;
        break;
      case 'settled':
        close('restless', restlessFrom, t);
        restlessFrom = null;
        break;
      case 'bed_exit':
        close('bed', bedFrom, t);
        close('restless', restlessFrom, t);
        bedFrom = restlessFrom = null;
        upFrom = t;
        break;
      case 'checkin_timeout':
        alerted = true;
        break;
      case 'checkin_result':
        if (e.data?.escalate) alerted = true;
        break;
      case 'got_up':
        close('bed', bedFrom, t);
        bedFrom = null;
        break;
    }
  }
  const last = hours(end);
  close('bed', bedFrom, last);
  close('restless', restlessFrom, last);
  close(alerted ? 'alert' : 'up', upFrom, last);
  // Restless bars sit on top of the in-bed bar they interrupt.
  return segments.sort((a, b) => Number(a.kind === 'restless') - Number(b.kind === 'restless'));
}

/** The "now" line on the ribbon, while the night is still going. */
export function ribbonNow(w: NightWindow, now: number): number | undefined {
  const h = (now - w.ribbonStart) / HOUR_MS;
  return w.over || h < 0 || h > RIBBON_HOURS ? undefined : h;
}

/**
 * Minutes asleep in a night, restless spells included: the in-bed span on the ribbon. Restless bars
 * sit on top of the in-bed bar they interrupt, so they only count where they outlast it.
 */
export function sleptMinutes(all: EventRow[], w: NightWindow): number {
  const segments = ribbonSegments(all, w, w.end);
  const hours = (kind: RibbonSegment['kind']) =>
    segments.filter((s) => s.kind === kind).reduce((h, s) => h + s.to - s.from, 0);
  return Math.max(hours('bed'), hours('restless')) * 60;
}

const TIMES = ['None', 'Once', 'Twice'];

/** The two stat tiles: time asleep, and how often she got up. */
export function nightStats(all: EventRow[], w: NightWindow, now: number) {
  const rows = within(all, w);
  const asleep = rows.find((e) => e.event_type === 'asleep');
  const gotUp = rows.find((e) => e.event_type === 'got_up');
  const trips = rows.filter((e) => e.event_type === 'bed_exit').length;
  const until = gotUp ? Date.parse(gotUp.device_ts) : Math.min(now, w.end);
  return {
    asleepLabel: gotUp || w.over ? 'Slept for' : 'Asleep for',
    asleepValue: asleep ? duration(until - Date.parse(asleep.device_ts)) : 'Not yet',
    tripsValue: TIMES[trips] ?? `${trips} times`,
  };
}

// ---------- the week ----------

export type NightTone = 'quiet' | 'checked' | 'alerted' | 'cold' | 'hot' | 'unknown';

export type NightSummary = {
  key: number;
  title: string;
  line: string;
  tone: NightTone;
  /** The night itself, for the week table and the night screen. */
  window: NightWindow;
};

/** A night the sleep charts mark with the orange cap: family were alerted, or the room got too cold or hot. */
export const isFlagged = (tone: NightTone) => tone === 'alerted' || tone === 'cold' || tone === 'hot';

const WORDS = ['no', 'once', 'twice'];

/**
 * One line per past night, newest first: quiet nights stay short, the exceptions say what happened.
 * The newest is called "Last night" only while tonight is still going; in the afternoon the
 * screen above already shows last night, so the list names every night by its weekday.
 */
export function weekSummaries(
  all: EventRow[],
  incidents: IncidentRow[],
  current: NightWindow,
  count: number,
  tz: string,
  name: string,
): NightSummary[] {
  return pastNights(current, count, tz).map((w, i) =>
    summariseNight(all, incidents, w, i === 0 && !current.over ? 'Last night' : weekday(w.start, tz), name),
  );
}

/** One night as a line of words and an outcome, for the summary card and the week. */
export function summariseNight(
  all: EventRow[],
  incidents: IncidentRow[],
  w: NightWindow,
  title: string,
  name: string,
): NightSummary {
  const rows = within(all, w);
  const incident = incidents.find((x) => {
    const t = Date.parse(x.opened_at);
    return t >= w.start && t < w.end;
  });
  if (incident) {
    const tone: NightTone = incident.kind === 'room_cold' ? 'cold' : incident.kind === 'room_hot' ? 'hot' : 'alerted';
    return {
      window: w,
      key: w.start,
      title,
      line: incident.summary ?? `${name} didn't come back to bed and family were alerted.`,
      tone,
    };
  }
  const trips = rows.filter((e) => e.event_type === 'bed_return').map((e) => Number(e.data?.trip_min ?? 0));
  const fine = rows.find((e) => e.event_type === 'checkin_result' && !e.data?.escalate);
  if (fine) {
    const longest = Math.max(...trips, 0);
    const reason = typeof fine.data?.reason === 'string' ? fine.data.reason : '';
    const said = reason
      ? `${reason.charAt(0).toUpperCase()}${reason.slice(1)}.`
      : `${name} answered the check-in and was fine.`;
    return {
      window: w,
      key: w.start,
      title,
      line: `Up for ${longest} min. ${said}`,
      tone: 'checked',
    };
  }
  if (!rows.length)
    return {
      window: w,
      key: w.start,
      title,
      line: 'Nothing from the pillow that night.',
      tone: 'unknown',
    };
  if (!trips.length)
    return {
      window: w,
      key: w.start,
      title,
      line: 'Slept through.',
      tone: 'quiet',
    };
  const times = trips.length < WORDS.length ? WORDS[trips.length] : `${trips.length} times`;
  const back = trips.length === 1 ? `back in ${trips[0]} min` : `back each time within ${Math.max(...trips)} min`;
  return {
    window: w,
    key: w.start,
    title,
    line: `Up ${times}, ${back}.`,
    tone: 'quiet',
  };
}

// ---------- today's reminders ----------

export type ReminderToday = {
  key: number;
  label: string;
  /** "8:00 am". */
  time: string;
  confirm: boolean;
  kind: Reminder['kind'];
  /** How it went, or "later" when its time hasn't come yet today. */
  status: Occurrence['status'] | 'later';
};

const WEEKDAY_ISO: Record<string, number> = {
  Mon: 1,
  Tue: 2,
  Wed: 3,
  Thu: 4,
  Fri: 5,
  Sat: 6,
  Sun: 7,
};

/** "08:00:00" as "8:00 am". */
function wallTime(hhmm: string): string {
  const [h, m] = hhmm.split(':').map(Number);
  return `${h % 12 || 12}:${String(m).padStart(2, '0')} ${h < 12 ? 'am' : 'pm'}`;
}

/**
 * Every reminder set for today on her clock, in time order, with what happened to the ones that
 * have come due. A reminder whose time has passed but has no result yet is still "waiting".
 */
export function todaysReminders(
  reminders: Reminder[],
  occurrences: Occurrence[],
  now: number,
  tz: string,
): ReminderToday[] {
  const day = WEEKDAY_ISO[formatter('short', tz, { weekday: 'short' }).format(new Date(now))];
  const { hour, minute } = partsIn(now, tz);
  const nowHHMM = `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`;
  return reminders
    .filter((r) => r.active && r.days.includes(day))
    .sort((a, b) => a.time_of_day.localeCompare(b.time_of_day))
    .map((r) => {
      const happened = occurrences.find((o) => o.reminder_id === r.id);
      const passed = r.time_of_day.slice(0, 5) <= nowHHMM;
      return {
        key: r.id,
        label: r.label.charAt(0).toUpperCase() + r.label.slice(1),
        time: wallTime(r.time_of_day),
        confirm: r.confirm,
        kind: r.kind,
        status: happened?.status ?? (passed ? 'waiting' : 'later'),
      };
    });
}

/** A past night by its start (the `key` of its summary), or the night in progress. */
export function nightAt(start: number, now: number, tz: string, count: number): NightWindow | null {
  const current = currentNight(now, tz);
  if (current.start === start) return current;
  return pastNights(current, count, tz).find((w) => w.start === start) ?? null;
}

/** "Tuesday night", or "Last night" / "Tonight" for the latest. */
export function nightTitle(w: NightWindow, now: number, tz: string): string {
  const current = currentNight(now, tz);
  if (w.start === current.start) return current.over ? 'Last night' : 'Tonight';
  if (!current.over && pastNights(current, 1, tz)[0].start === w.start) return 'Last night';
  return `${weekday(w.start, tz)} night`;
}

/** "21 October". */
export function nightDate(w: NightWindow, tz: string): string {
  return formatter('date', tz, { day: 'numeric', month: 'long' }, 'en-GB').format(new Date(w.start));
}

/** "Tue". */
export function shortDay(w: NightWindow, tz: string): string {
  return formatter('short', tz, { weekday: 'short' }).format(new Date(w.start));
}

/** The week table's columns: when she went to bed, how often she got up, when she woke. */
export function nightFacts(all: EventRow[], w: NightWindow, tz: string) {
  const rows = within(all, w);
  const inBed = rows.find((e) => e.event_type === 'lay_down');
  const woke = rows.find((e) => e.event_type === 'got_up');
  const trips = rows.filter((e) => e.event_type === 'bed_exit').length;
  return {
    inBed: inBed ? clockTime(inBed.device_ts, tz) : null,
    woke: woke ? clockTime(woke.device_ts, tz) : null,
    trips,
    tripsWord: trips === 0 ? 'No' : trips === 1 ? 'Once' : trips === 2 ? 'Twice' : `${trips} times`,
  };
}

/** What each event means, said plainly, for the night's timeline. Unlisted kinds are left out. */
const EVENT_WORDS: Record<string, (e: EventRow) => string> = {
  lay_down: () => 'Lay down',
  asleep: () => 'Fell asleep',
  restless: () => 'Restless',
  settled: () => 'Settled again',
  bed_exit: () => 'Got out of bed',
  bed_return: (e) => (e.data?.trip_min ? `Back in bed after ${String(e.data.trip_min)} min` : 'Back in bed'),
  checkin_start: () => 'The pillow checked in',
  checkin_result: (e) => (e.data?.escalate ? 'No answer, family alerted' : 'Answered the pillow'),
  checkin_timeout: () => 'No answer, family alerted',
  got_up: () => 'Up for the day',
};

export type TimelineEntry = {
  key: string;
  time: string;
  what: string;
  notable: boolean;
};

/** The night's events in order, as a time and words. Notable ones are the exceptions: trips and alerts. */
export function nightTimeline(all: EventRow[], w: NightWindow, tz: string): TimelineEntry[] {
  return within(all, w).flatMap((e, i) => {
    const say = EVENT_WORDS[e.event_type];
    if (!say) return [];
    const notable =
      ['bed_exit', 'checkin_start', 'checkin_timeout'].includes(e.event_type) || Boolean(e.data?.escalate);
    return [
      {
        key: `${i}-${e.device_ts}`,
        time: clockTime(e.device_ts, tz),
        what: say(e),
        notable,
      },
    ];
  });
}
