/** Settings > Alerts: how the signed-in family member is reached when someone they look after needs help. */

import { api } from '@/services/api';

/** The ways an alert reaches this person: the red alert and buzz on this phone, a text, a call. */
export type AlertSwitch = 'app' | 'sms' | 'call';

export type AlertPrefs = Record<AlertSwitch, boolean> & {
  /** Their mobile in E.164 ("+447700900123"), or null before they add one. */
  phone: string | null;
  /** A gentle notice in the app when she's restless (never a text or a call). */
  restless: boolean;
  /** Off call, or inside their quiet hours, they are alerted after the others, never left out. */
  on_call: boolean;
  /** Their quiet hours as "HH:MM" on her clock, or null for none. */
  quiet_start: string | null;
  quiet_end: string | null;
  /** Whether the server can send texts and calls at all. */
  twilio_ready: boolean;
};

export type AlertPrefsPatch = Partial<Omit<AlertPrefs, 'twilio_ready'>>;

export type AlertTestResult = { sent: boolean; via: 'imessage' | 'sms' | 'call' | null; error: string | null };

/** A mobile number as the backend stores it, or null when it can't be one (no country code, too short). */
export function toE164(typed: string): string | null {
  let number = typed.replace(/[\s\-().]/g, '');
  if (!number.startsWith('+')) number = `+${number.replace(/^00/, '')}`;
  return /^\+[1-9]\d{7,14}$/.test(number) ? number : null;
}

export const getAlertPrefs = () => api<AlertPrefs>('/me/alerts');

export const saveAlertPrefs = (patch: AlertPrefsPatch) => api<AlertPrefs>('/me/alerts', { method: 'PATCH', body: patch });

/** Test accounts only: start a real alert on the pillow now (red screen, buzz, then texts and calls). */
export const startDebugAlert = (pillowId: string) =>
  api<{ night_state: string }>(`/pillows/${pillowId}/alert-debug/start`, { method: 'POST' });

/** Test accounts only: end the pillow's alert as if she said she's fine. */
export const stopDebugAlert = (pillowId: string) =>
  api<{ night_state: string }>(`/pillows/${pillowId}/alert-debug/stop`, { method: 'POST' });

/** Test accounts only: a reminder due now that the pillow's bedside voice says, as a demo. */
export const startDebugReminder = (pillowId: string) =>
  api<{ night_state: string }>(`/pillows/${pillowId}/alert-debug/reminder`, { method: 'POST' });

/** Whether the pillow waits `minutes` after a check-in before checking on her again. */
export type CheckinCooldown = { on: boolean; minutes: number };

/** Test accounts only: read the wait between check-ins. */
export const getCheckinCooldown = (pillowId: string) =>
  api<CheckinCooldown>(`/pillows/${pillowId}/alert-debug/cooldown`);

/** Test accounts only: turn the wait between check-ins on, or off so the pillow asks every time. */
export const setCheckinCooldown = (pillowId: string, on: boolean) =>
  api<CheckinCooldown>(`/pillows/${pillowId}/alert-debug/cooldown`, { method: 'PUT', body: { on } });

/** Send one test text or call to this person's own number now. */
export const sendTestAlert = (channel: 'sms' | 'call') =>
  api<AlertTestResult>('/me/alerts/test', { method: 'POST', body: { channel } });
