/** Auth copy and rules. Failure messages never reveal whether an account exists. */

/** Shown for every rejected login: unknown user, wrong password and unconfirmed email alike. */
export const LOGIN_FAILED_MESSAGE = 'Details incorrect';

/** Shown when the auth server cannot be reached; says nothing about the account. */
export const LOGIN_UNREACHABLE_MESSAGE = 'Could not reach the server. Try again.';

/** Shown when a field is left blank, before anything is sent. */
export const LOGIN_MISSING_FIELDS_MESSAGE = 'Enter your email and password';

/** Shown when the email has no @, before anything is sent. */
export const INVALID_EMAIL_MESSAGE = "That doesn't look like an email address";

/** Sign-up failures. Unlike login, a taken email has to be said, or the person would never know to log in. */
export const SIGNUP_TAKEN_MESSAGE = 'There is already an account with that email. Log in instead.';
export const SIGNUP_WEAK_PASSWORD_MESSAGE = 'Use a longer password, at least 8 characters.';
export const SIGNUP_FAILED_MESSAGE = "Couldn't create the account. Try again.";

/** Shown when the account exists but Supabase wants it confirmed before the first login. */
export const SIGNUP_NEEDS_CONFIRMATION_MESSAGE = 'Account created. Confirm it from your email, then log in.';

/** Checked here before sending, so the rule is the same whatever the Supabase project allows. */
export const MIN_PASSWORD_LENGTH = 8;
