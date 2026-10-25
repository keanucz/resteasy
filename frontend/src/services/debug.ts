/**
 * Test-account tools. `contacts.is_test` marks a test login in Supabase; only those accounts see
 * the alert simulator, and the database refuses everyone else whatever the app does.
 */

import { supabase } from '@/services/supabase/client';

/** The rungs the simulator can play, in the order a real night climbs them. */
export const SIMULATED_ALERTS = [
  { level: 'up', label: 'Out of bed' },
  { level: 'checkin', label: 'Pillow checks in' },
  { level: 'alert_first', label: 'First contact alerted' },
  { level: 'alert_everyone', label: 'Everyone alerted' },
  { level: 'cold', label: 'Cold room' },
  { level: 'clear', label: 'Back in bed, clear alerts' },
] as const;

export type SimulatedAlert = (typeof SIMULATED_ALERTS)[number]['level'];

/** True when this login is a test account. False on any error. */
export async function isTestAccount(): Promise<boolean> {
  const { data, error } = await supabase.rpc('am_i_test');
  return !error && data === true;
}

/** Plays one rung on the pillow and returns what happened, in words. Throws a sentence on failure. */
export async function simulateAlert(pillowId: string, level: SimulatedAlert): Promise<string> {
  const { data, error } = await supabase.rpc('simulate_alert', { p_pillow: pillowId, p_level: level });
  if (error) throw new Error(error.message);
  return String(data);
}
