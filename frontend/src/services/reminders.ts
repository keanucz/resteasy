/**
 * The family's spoken reminders for one pillow (the backend's Routine agent plays them). New ones,
 * and changes to what is said or when, wait for the resident to agree out loud before they play.
 */

import { api } from '@/services/api';

export type ReminderKind = 'meds' | 'call' | 'custom';
/** Only voice is delivered today; SMS and email are kept for later. */
export type Channel = 'voice' | 'sms' | 'email';
export type Consent = 'pending' | 'agreed' | 'declined';
export type OccurrenceStatus = 'waiting' | 'due' | 'announced' | 'done' | 'missed';

/** ISO weekdays, 1 = Monday to 7 = Sunday. */
export const EVERY_DAY = [1, 2, 3, 4, 5, 6, 7];
export const WEEKDAYS = [1, 2, 3, 4, 5];

/** A reminder as the family set it up: one-off on `on_date`, else on `days` each week. */
export type Reminder = {
  id: number;
  label: string;
  kind: ReminderKind;
  time_of_day: string;
  days: number[];
  on_date: string | null;
  skip_dates: string[];
  channels: Channel[];
  confirm: boolean;
  active: boolean;
  consent: Consent;
  consent_at: string | null;
  created_by_name: string | null;
};

export type NewReminder = {
  label: string;
  kind?: ReminderKind;
  time_of_day: string;
  days?: number[];
  on_date?: string | null;
  confirm?: boolean;
  channels?: Channel[];
};

export type ReminderChange = Partial<NewReminder> & { active?: boolean; skip_dates?: string[] };

/** One time a reminder plays (or would, once she agrees) in a calendar range. */
export type CalendarEntry = {
  reminder_id: number;
  date: string;
  due_at: string;
  label: string;
  kind: ReminderKind;
  confirm: boolean;
  consent: Consent;
  recurring: boolean;
  status: OccurrenceStatus | null;
};

/** The longest range one calendar read may cover. */
export const CALENDAR_MAX_DAYS = 42;

const base = (pillowId: string) => `/pillows/${pillowId}/reminders`;

export const listReminders = (pillowId: string) => api<Reminder[]>(base(pillowId));

export const createReminder = (pillowId: string, reminder: NewReminder) =>
  api<Reminder>(base(pillowId), { method: 'POST', body: reminder });

export const updateReminder = (pillowId: string, id: number, change: ReminderChange) =>
  api<Reminder>(`${base(pillowId)}/${id}`, { method: 'PATCH', body: change });

export const deleteReminder = (pillowId: string, id: number) =>
  api<null>(`${base(pillowId)}/${id}`, { method: 'DELETE' });

/** Every time a reminder plays from `start` to `end` (YYYY-MM-DD, both included). */
export const readCalendar = (pillowId: string, start: string, end: string) =>
  api<CalendarEntry[]>(`${base(pillowId)}/calendar?start=${start}&end=${end}`);

/**
 * Moves one day of a recurring reminder: that day is skipped, and a one-off copy plays on `date` at
 * `time` instead. Both changes wait for her to agree again.
 */
export async function moveOneDay(pillowId: string, reminder: Reminder, from: string, date: string, time: string) {
  const copy = await createReminder(pillowId, {
    label: reminder.label,
    kind: reminder.kind,
    time_of_day: time,
    on_date: date,
    confirm: reminder.confirm,
    channels: reminder.channels,
  });
  await updateReminder(pillowId, reminder.id, { skip_dates: [...reminder.skip_dates, from] });
  return copy;
}
