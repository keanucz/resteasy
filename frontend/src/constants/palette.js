/**
 * The style guide's colours, the single source of truth (picked in the moodboard, Oct 2026).
 * tailwind.config.js turns `raw` into fixed classes (bg-night) and `modes` into theme-aware classes
 * (bg-canvas) that switch between dark and light; theme.ts re-exports both for code that cannot
 * take a className (Switch, StatusBar, SVG).
 */

/** Fixed colours. Prefer the theme-aware roles in `modes`; reach for these only when a surface is always one mode. */
const raw = {
  night: '#171537', // dark-mode background
  dusk: '#2A2752', // dark-mode cards and fields
  mist: '#EEEFF6', // dark-mode text
  glow: '#9499E6', // the accent on dark surfaces
  calm: '#9FD6C2', // "all good"
  alert: '#E64C6B', // escalation only, never decoration
  'night-muted': '#A39EAB', // secondary text on dark
  line: '#433F65', // borders on dark
  day: '#F5F6FE', // light-mode background
  'day-card': '#FFFFFF', // light-mode cards
  'day-field': '#EBECF7', // light-mode fields
  'day-line': '#DCDDEF', // borders on light
  'day-muted': '#6C697E', // secondary text on light
  'glow-day': '#686CB5', // the accent as a fill on light surfaces
  'glow-day-text': '#6266AF', // the accent as text on light surfaces
};

/**
 * State colours, used as text only (no fills, no pills). Same hue per state, pale on dark and
 * deep on light; every one is at least 4.5:1 on its surface.
 */
const states = {
  dark: { asleep: raw.calm, restless: '#E2A8F5', up: '#F4C46C', alert: '#FF9C94', offline: '#B8BAC6' },
  light: { asleep: '#0F7C66', restless: '#8E3BB3', up: '#A85C00', alert: '#C8202F', offline: '#5C6178' },
};

/**
 * The logo's colours, one per part, so the mark can be recoloured here without touching its paths.
 * Tailwind also exposes them as fill-logo-* / bg-logo-* classes; Logo.tsx reads them by name.
 */
const logo = {
  'logo-sky-top': '#121C48', // badge gradient, top
  'logo-sky-bottom': '#284A8E', // badge gradient, bottom
  'logo-spines': raw.glow,
  'logo-face': raw.mist,
  'logo-ink': raw.night, // eye and nose
  'logo-cheek': raw.glow,
  'logo-blanket': '#B9C8FF',
  'logo-fold': raw.glow,
  'logo-sparkle': raw.mist,
  'logo-sparkle-small': '#B9C8FF',
};

/** Theme roles. Components use these (bg-canvas, text-ink) so they work in both modes untouched. */
const modes = {
  dark: {
    canvas: raw.night, // screen background
    surface: raw.dusk, // cards, rows, tiles, dialogs
    field: raw.dusk, // text inputs
    ink: raw.mist, // main text
    'ink-muted': raw['night-muted'], // secondary text
    hairline: raw.line, // borders and dividers
    accent: raw.glow, // primary buttons, selected chips, switches
    'on-accent': raw.night, // text on accent fills
    'accent-text': raw.glow, // accent used as text (ghost buttons, links)
    danger: raw.alert, // alert buttons
    'on-danger': '#FFFFFF',
    'danger-text': states.dark.alert, // error messages
    calm: raw.calm, // ticked checkboxes
    'on-calm': raw.night,
    bone: '#3A3862', // skeleton placeholders: ink at 10% over surface
    'state-asleep': states.dark.asleep,
    'state-restless': states.dark.restless,
    'state-up': states.dark.up,
    'state-alert': states.dark.alert,
    'state-offline': states.dark.offline,
  },
  light: {
    canvas: raw.day,
    surface: raw['day-card'],
    field: raw['day-field'],
    ink: raw.night,
    'ink-muted': raw['day-muted'],
    hairline: raw['day-line'],
    accent: raw['glow-day'],
    'on-accent': '#FFFFFF',
    'accent-text': raw['glow-day-text'],
    danger: raw.alert,
    'on-danger': '#FFFFFF',
    'danger-text': states.light.alert,
    calm: raw.calm,
    'on-calm': raw.night,
    bone: '#EBEBF0', // ink at 7% over surface
    'state-asleep': states.light.asleep,
    'state-restless': states.light.restless,
    'state-up': states.light.up,
    'state-alert': states.light.alert,
    'state-offline': states.light.offline,
  },
};

module.exports = { raw, states, modes, logo };
