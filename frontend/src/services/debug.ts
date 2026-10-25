/**
 * Test-account tools. `contacts.is_test` marks a test login in Supabase; only those accounts see
 * the alert debug buttons, and the backend refuses everyone else whatever the app does.
 */

import { supabase } from '@/services/supabase/client';

/** True when this login is a test account. False on any error. */
export async function isTestAccount(): Promise<boolean> {
  const { data, error } = await supabase.rpc('am_i_test');
  return !error && data === true;
}
