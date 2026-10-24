/** Sign in and out with Supabase Auth, translating every failure into a non-revealing message. */

import { isAuthRetryableFetchError } from '@supabase/supabase-js';

import {
  INVALID_EMAIL_MESSAGE,
  LOGIN_FAILED_MESSAGE,
  LOGIN_MISSING_FIELDS_MESSAGE,
  LOGIN_UNREACHABLE_MESSAGE,
  MIN_PASSWORD_LENGTH,
  SIGNUP_FAILED_MESSAGE,
  SIGNUP_NEEDS_CONFIRMATION_MESSAGE,
  SIGNUP_TAKEN_MESSAGE,
  SIGNUP_WEAK_PASSWORD_MESSAGE,
} from '@/constants/auth';
import { supabase } from '@/services/supabase/client';

export type SignInResult = { ok: true } | { ok: false; message: string };

/** Emails are matched case-insensitively and typed with stray spaces, so compare a trimmed lower-case copy. */
function normaliseEmail(email: string): string {
  return email.trim().toLowerCase();
}

/** The message for fields that cannot be sent as they are, or null when they can. */
function checkFields(email: string, password: string): string | null {
  if (!email.trim() || !password) return LOGIN_MISSING_FIELDS_MESSAGE;
  if (!email.includes('@')) return INVALID_EMAIL_MESSAGE;
  return null;
}

/** Sign in with an email and password. On success the session is stored automatically. */
export async function signIn(email: string, password: string): Promise<SignInResult> {
  const invalid = checkFields(email, password);
  if (invalid) return { ok: false, message: invalid };
  const { error } = await supabase.auth.signInWithPassword({ email: normaliseEmail(email), password });
  if (!error) {
    return { ok: true };
  }
  return { ok: false, message: isAuthRetryableFetchError(error) ? LOGIN_UNREACHABLE_MESSAGE : LOGIN_FAILED_MESSAGE };
}

/**
 * Create an account with an email and password. When the Supabase project returns a session the
 * user is signed in straight away; if it wants confirmation first, the result says so.
 */
export async function signUp(email: string, password: string): Promise<SignInResult> {
  const invalid = checkFields(email, password);
  if (invalid) return { ok: false, message: invalid };
  if (password.length < MIN_PASSWORD_LENGTH) {
    return { ok: false, message: SIGNUP_WEAK_PASSWORD_MESSAGE };
  }
  const { data, error } = await supabase.auth.signUp({ email: normaliseEmail(email), password });
  if (error) {
    if (isAuthRetryableFetchError(error)) return { ok: false, message: LOGIN_UNREACHABLE_MESSAGE };
    if (error.code === 'user_already_exists') return { ok: false, message: SIGNUP_TAKEN_MESSAGE };
    if (error.code === 'weak_password') return { ok: false, message: SIGNUP_WEAK_PASSWORD_MESSAGE };
    return { ok: false, message: SIGNUP_FAILED_MESSAGE };
  }
  // With confirmations on, Supabase hides an existing account behind a user with no identities.
  if (data.user && data.user.identities?.length === 0) return { ok: false, message: SIGNUP_TAKEN_MESSAGE };
  if (!data.session) return { ok: false, message: SIGNUP_NEEDS_CONFIRMATION_MESSAGE };
  return { ok: true };
}

/** End the session on this device. */
export async function signOut(): Promise<void> {
  await supabase.auth.signOut();
}
