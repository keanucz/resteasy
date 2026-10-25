/** The pillow the app shows, and the rules for reading its state. */

/**
 * Pairing is mocked for now: "Connect pillow" links the login's own pillow (GET /api/me), and a
 * login that isn't anyone's contact yet gets the demo household's pillow, Margaret's.
 */
export const DEMO_PILLOW_ID = 'mum';

/** Pretend pairing steps, shown one after the other while "connecting". */
export const CONNECT_STEPS = ['Looking for the pillow', 'Connecting to the pillow', 'Reading the first night'] as const;
export const CONNECT_STEP_MS = 900;

/** The device reports twice a second while on; silence for this long means the pillow is offline. */
export const OFFLINE_AFTER_MS = 2 * 60 * 1000;

/** The ribbon's night window in the resident's clock: 10 pm to 7 am. */
export const RIBBON_START_HOUR = 22;
export const RIBBON_HOURS = 9;

/** A "night" for grouping events runs from 6 pm to noon; before 6 pm the app shows last night. */
export const NIGHT_STARTS_HOUR = 18;
export const NIGHT_ENDS_HOUR = 12;

/** How many past nights the week list shows. */
export const WEEK_NIGHTS = 7;

/** How many past nights the month chart (and the night screen) can reach back to. */
export const MONTH_NIGHTS = 28;

/** Where the "connected" flag lives on this device, per login. */
export const LINK_STORAGE_PREFIX = 'rest-easy:pillow:';

/** Minutes up before the check-in; the backend's Guardian allows 10 to 30 and rejects the rest (422). */
export const CHECKIN_MIN_WAIT = 10;
export const CHECKIN_MAX_WAIT = 30;

/** How long "Saved" stays under a setting after a save goes through. */
export const SAVED_NOTE_MS = 2000;
