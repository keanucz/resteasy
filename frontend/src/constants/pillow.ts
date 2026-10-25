/** The pillow the app shows, and the rules for reading its state. */

/**
 * "Connect pillow" links the login's own pillow (GET /api/me). A login that looks after nobody yet
 * names the person first, and the backend sets the pillow up for them (POST /api/me/pillows).
 * Shown when that fails, usually because the backend can't be reached.
 */
export const CONNECT_FAILED = "Couldn't reach Rest Easy. Check your phone's connection and try again.";

/** POST /api/me/pillows answered 409: another login has already set the pillow up. */
export const PILLOW_TAKEN = 'This pillow is already set up on another account. Sign in with that account instead.';

/** Longest name for the person the pillow is for; the backend refuses longer ones. */
export const RESIDENT_NAME_MAX = 60;

/**
 * Then it pings the pillow (POST /api/pillows/{id}/ping) and only links it once both boards answer:
 * the sensors inside the pillow and the bedside speaker unit they talk through.
 */
export const PILLOW_SILENT = "The pillow isn't answering. Check it's plugged in, then try again.";
export const SPEAKER_SILENT = "The pillow is on, but its bedside speaker isn't answering. Check it's plugged in, then try again.";

/** Pairing steps, shown one after the other while "connecting". */
export const CONNECT_STEPS = ['Looking for the pillow', 'Connecting to the pillow', 'Reading the first night'] as const;
export const CONNECT_STEP_MS = 900;

/** The device reports twice a second while on; silence for this long means the pillow is offline. */
export const OFFLINE_AFTER_MS = 2 * 60 * 1000;

/** While the pillow is offline, the app pings it this often to see which part isn't answering. */
export const PING_EVERY_MS = 5000;

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
