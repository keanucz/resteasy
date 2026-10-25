/** Settings > Alerts: how the signed-in family member is reached when someone they look after needs help. */

import { api } from '@/services/api';

/** The ways an alert reaches this person: the red alert and buzz on this phone, a text, a call. */
export type AlertSwitch = 'app' | 'sms' | 'call';

export type AlertPrefs = Record<AlertSwitch, boolean> & {
  /** Their mobile in E.164 ("+447700900123"), or null before they add one. */
  phone: string | null;
  /** Whether the server can send texts and calls at all. */
  twilio_ready: boolean;
};

export type AlertPrefsPatch = Partial<Pick<AlertPrefs, 'phone' | AlertSwitch>>;

export type AlertTestResult = { sent: boolean; via: 'imessage' | 'sms' | 'call' | null; error: string | null };

/** A mobile number as the backend stores it, or null when it can't be one (no country code, too short). */
export function toE164(typed: string): string | null {
  let number = typed.replace(/[\s\-().]/g, '');
  if (!number.startsWith('+')) number = `+${number.replace(/^00/, '')}`;
  return /^\+[1-9]\d{7,14}$/.test(number) ? number : null;
}

export const getAlertPrefs = () => api<AlertPrefs>('/me/alerts');

export const saveAlertPrefs = (patch: AlertPrefsPatch) => api<AlertPrefs>('/me/alerts', { method: 'PATCH', body: patch });

/** Send one test text or call to this person's own number now. */
export const sendTestAlert = (channel: 'sms' | 'call') =>
  api<AlertTestResult>('/me/alerts/test', { method: 'POST', body: { channel } });
