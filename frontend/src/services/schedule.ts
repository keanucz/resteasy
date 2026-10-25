/**
 * Reminders on her clock: calendar dates as "YYYY-MM-DD", times as "HH:MM", and the words the app
 * uses for them ("Tomorrow at 8:00 am", "every Mon and Wed"). Dates are plain strings so a day never
 * shifts with the phone's own time zone.
 */

import {
  type CalendarEntry,
  type Consent,
  EVERY_DAY,
  type OccurrenceStatus,
  type Reminder,
  WEEKDAYS,
} from '@/services/reminders';

/** Drag and the time list both move in quarter hours. */
export const SNAP_MIN = 15;

/** One time a reminder plays, with its time on her clock. */
export type Slot = CalendarEntry & { time: string };

const DAY_MS = 24 * 60 * 60 * 1000;
const SHORT_DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const LONG_DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const LONG_MONTHS = [
  'January',
  'February',
  'March',
  'April',
  'May',
  'June',
  'July',
  'August',
  'September',
  'October',
  'November',
  'December',
];

const pad = (n: number) => String(n).padStart(2, '0');
const toUtc = (date: string) =>
  Date.UTC(Number(date.slice(0, 4)), Number(date.slice(5, 7)) - 1, Number(date.slice(8, 10)));
const fromUtc = (ms: number) => {
  const d = new Date(ms);
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}`;
};

/** The calendar date at `ms` on the clock of `tz`. */
export function dateIn(ms: number, tz: string): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone: tz, year: 'numeric', month: '2-digit', day: '2-digit' }).format(
    new Date(ms),
  );
}

/** "HH:MM" at `ms` on the clock of `tz`. */
export function clockIn(ms: number, tz: string): string {
  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone: tz,
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(new Date(ms));
  const get = (type: string) => parts.find((p) => p.type === type)?.value ?? '00';
  return `${get('hour')}:${get('minute')}`;
}

export const addDays = (date: string, days: number) => fromUtc(toUtc(date) + days * DAY_MS);
export const daysBetween = (from: string, to: string) => Math.round((toUtc(to) - toUtc(from)) / DAY_MS);

/** ISO weekday of a date, 1 = Monday to 7 = Sunday. */
export function isoWeekday(date: string): number {
  return ((new Date(toUtc(date)).getUTCDay() + 6) % 7) + 1;
}

/** The Monday of the week `date` is in. */
export const weekStart = (date: string) => addDays(date, 1 - isoWeekday(date));

/** "Thu", or "Thursday" when `long`. */
export const dayName = (date: string, long = false) => (long ? LONG_DAYS : SHORT_DAYS)[isoWeekday(date) - 1];

/** "30 Oct". */
export const dayMonth = (date: string) => `${Number(date.slice(8, 10))} ${MONTHS[Number(date.slice(5, 7)) - 1]}`;

/** "20 to 26 October", or "27 October to 2 November" across a month end. */
export function weekRange(start: string): string {
  const end = addDays(start, 6);
  const month = (d: string) => LONG_MONTHS[Number(d.slice(5, 7)) - 1];
  const day = (d: string) => Number(d.slice(8, 10));
  return month(start) === month(end)
    ? `${day(start)} to ${day(end)} ${month(end)}`
    : `${day(start)} ${month(start)} to ${day(end)} ${month(end)}`;
}

/** "Today", "Tomorrow", "Thursday" within the week ahead, else "Thu 6 Nov". */
export function relativeDay(date: string, today: string): string {
  const ahead = daysBetween(today, date);
  if (ahead === 0) return 'Today';
  if (ahead === 1) return 'Tomorrow';
  if (ahead === -1) return 'Yesterday';
  if (ahead > 1 && ahead < 7) return dayName(date, true);
  return `${dayName(date)} ${dayMonth(date)}`;
}

/** "today", "tomorrow" or "this Thursday": one day of a reminder that repeats. */
export function thisDay(date: string, today: string): string {
  const day = relativeDay(date, today);
  return day === 'Today' || day === 'Tomorrow' ? day.toLowerCase() : `this ${dayName(date, true)}`;
}

/** "22:00" as "10:00 pm". */
export function formatClock(hhmm: string): string {
  const hour = Number(hhmm.slice(0, 2));
  return `${hour % 12 || 12}:${hhmm.slice(3, 5)} ${hour < 12 ? 'am' : 'pm'}`;
}

/** "08:00" as "8 am" and "18:30" as "6:30 pm": a time as it is said out loud. */
export function spokenClock(hhmm: string): string {
  const [h, m] = hhmm.split(':').map(Number);
  return `${h % 12 || 12}${m ? `:${pad(m)}` : ''} ${h < 12 ? 'am' : 'pm'}`;
}

/** "Today at 8:00 am" as "today at 8:00 am", for the middle of a sentence. Day names keep their capital. */
export const lowerDay = (words: string) => words.replace(/^(Today|Tomorrow|Yesterday)/, (w) => w.toLowerCase());

/** "Tomorrow at 8:00 am". */
export const whenWords = (date: string, time: string, today: string) =>
  `${relativeDay(date, today)} at ${formatClock(time)}`;

/** "08:00:00" or "08:00" as "08:00". */
export const hhmm = (time: string) => time.slice(0, 5);

export const minutesOf = (time: string) => Number(time.slice(0, 2)) * 60 + Number(time.slice(3, 5));
export const timeOf = (minutes: number) => `${pad(Math.floor(minutes / 60))}:${pad(minutes % 60)}`;

const sameDays = (a: number[], b: number[]) => a.length === b.length && a.every((d, i) => d === b[i]);

/** How often it plays, in words: "every day", "on weekdays", "every Mon and Wed", "once, on Thu 30 Oct". */
export function repeatWords(r: Pick<Reminder, 'days' | 'on_date'>, today: string): string {
  if (r.on_date) {
    const ahead = daysBetween(today, r.on_date);
    return ahead >= 0 && ahead < 2
      ? `once, ${relativeDay(r.on_date, today).toLowerCase()}`
      : `once, on ${dayName(r.on_date)} ${dayMonth(r.on_date)}`;
  }
  const days = [...r.days].sort();
  if (sameDays(days, EVERY_DAY)) return 'every day';
  if (sameDays(days, WEEKDAYS)) return 'on weekdays';
  if (sameDays(days, [6, 7])) return 'at weekends';
  const names = days.map((d) => SHORT_DAYS[d - 1]);
  return `every ${names.length > 1 ? `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}` : names[0]}`;
}

/**
 * A label as the pillow will say it: trimmed, without a full stop, and without a leading "it's
 * time to" (the pillow adds that itself).
 */
export function tidyLabel(label: string): string {
  return label
    .trim()
    .replace(/^(it'?s |it is )?time to\s+/i, '')
    .replace(/[.!\s]+$/, '');
}

/** The sentence she hears, exactly as the backend's Routine agent builds it. */
export const spokenLine = (name: string, label: string) => `${name}, it's time to ${tidyLabel(label)}.`;

/** "Saturday 1 November", as the pillow says a date. */
export const spokenDate = (date: string) =>
  `${LONG_DAYS[isoWeekday(date) - 1]} ${Number(date.slice(8, 10))} ${LONG_MONTHS[Number(date.slice(5, 7)) - 1]}`;

/** "every day", "on weekdays", "on weekends", "on Mondays and Thursdays", as the pillow says them. */
export function spokenDays(days: number[]): string {
  const sorted = [...days].sort();
  if (sameDays(sorted, EVERY_DAY)) return 'every day';
  if (sameDays(sorted, WEEKDAYS)) return 'on weekdays';
  if (sameDays(sorted, [6, 7])) return 'on weekends';
  const plural = sorted.map((d) => `${LONG_DAYS[d - 1]}s`);
  return `on ${plural.length === 1 ? plural[0] : `${plural.slice(0, -1).join(', ')} and ${plural[plural.length - 1]}`}`;
}

/**
 * The question the pillow asks before a reminder ever plays, word for word as the backend's
 * Routine agent builds it: "Sam would like to remind you to take your tablets at 8 am every day.
 * Is that alright?". `asker` is the family member's full name; with none it says "Your family".
 */
export function consentQuestion(
  asker: string | null,
  label: string,
  time: string,
  days: number[],
  onDate: string | null,
): string {
  const who = asker?.trim().split(/\s+/)[0] || 'Your family';
  const on = onDate ? `on ${spokenDate(onDate)}` : spokenDays(days);
  return `${who} would like to remind you to ${label} at ${spokenClock(time)} ${on}. Is that alright?`;
}

/** "take your tablets" as "Take your tablets", for titles. */
export const capitalise = (text: string) => text.charAt(0).toUpperCase() + text.slice(1);

/** Consent in words, or null once she has agreed (the quiet default needs no words). */
export function consentWords(consent: Consent, name: string): string | null {
  if (consent === 'pending') return `Waiting for ${name} to agree`;
  if (consent === 'declined') return `${name} said no, so it won't play`;
  return null;
}

/**
 * A reminder as the app uses it, whatever the backend's age: older backends send "HH:MM:SS" and
 * have no consent, one-off dates or skips yet. Those reminders already play, so they count as agreed.
 */
export function normaliseReminder(raw: Partial<Reminder> & Pick<Reminder, 'id' | 'label' | 'time_of_day'>): Reminder {
  return {
    id: raw.id,
    label: raw.label,
    kind: raw.kind ?? 'custom',
    time_of_day: hhmm(raw.time_of_day),
    days: raw.days ?? EVERY_DAY,
    on_date: raw.on_date ?? null,
    skip_dates: raw.skip_dates ?? [],
    channels: raw.channels ?? ['voice'],
    confirm: raw.confirm ?? false,
    active: raw.active ?? true,
    consent: raw.consent ?? 'agreed',
    consent_at: raw.consent_at ?? null,
    created_by_name: raw.created_by_name ?? null,
  };
}

/** A calendar entry with its time on her clock (from `due_at`, else the reminder's own time). */
export function toSlot(entry: CalendarEntry, tz: string, fallbackTime?: string): Slot {
  const due = Date.parse(entry.due_at);
  return { ...entry, time: Number.isNaN(due) ? (fallbackTime ?? '00:00') : clockIn(due, tz) };
}

/**
 * The calendar worked out on the phone, for backends without GET /calendar: every day from
 * `start` to `end` that each active reminder plays on. Only today's results are known
 * (`today` holds them by reminder), so other days carry no status.
 */
export function expandCalendar(
  reminders: Reminder[],
  start: string,
  end: string,
  today: { date: string; status: Map<number, OccurrenceStatus> },
): Slot[] {
  const slots: Slot[] = [];
  for (let date = start; date <= end; date = addDays(date, 1)) {
    for (const r of reminders) {
      if (!r.active || r.skip_dates.includes(date)) continue;
      const plays = r.on_date ? r.on_date === date : r.days.includes(isoWeekday(date));
      if (!plays) continue;
      slots.push({
        reminder_id: r.id,
        date,
        due_at: `${date}T${r.time_of_day}:00`,
        label: r.label,
        kind: r.kind,
        confirm: r.confirm,
        consent: r.consent,
        recurring: !r.on_date,
        status: date === today.date ? (today.status.get(r.id) ?? null) : null,
        time: r.time_of_day,
      });
    }
  }
  return slots.sort((a, b) => (a.date + a.time).localeCompare(b.date + b.time));
}

/**
 * The weekdays after moving a recurring reminder "every time" from one day to another: every day
 * stays every day (only the time moves), otherwise the old weekday becomes the new one.
 */
export function shiftDays(days: number[], from: string, to: string): number[] {
  if (sameDays([...days].sort(), EVERY_DAY)) return EVERY_DAY;
  const a = isoWeekday(from);
  const b = isoWeekday(to);
  if (a === b) return days;
  return [...new Set(days.map((d) => (d === a ? b : d)))].sort();
}

/** Whether a time on a date has already gone by on her clock. */
export const isPast = (date: string, time: string, today: string, now: string) =>
  date < today || (date === today && time <= now);
