import { Easing } from 'react-native-reanimated';

/**
 * Motion tokens. Calm by default: motion answers an action or a state change and never decorates.
 * Alerts get less choreography, not more. Nothing bounces.
 */

/** Durations in ms. Only the sky is slow; it is the one signature moment. */
export const DURATION = {
  instant: 90, // press-in, toggle thumb
  fast: 150, // press-out, focus, chip and tab selection, alert dialog
  base: 220, // error in, dialog in, list item in
  slow: 320, // first data fading in, headline word change
  sky: 700, // calm sky crossfade, and an alert resolving (relief should land slowly)
  skyAlert: 250, // any change into alert: the fact, now
  exit: 160, // leaving, about 70% of entering
} as const;

/** Ease out when things enter, ease in when they leave. */
export const EASE = {
  out: Easing.bezier(0.2, 0, 0, 1), // cubic-bezier(0.2, 0, 0, 1)
  in: Easing.bezier(0.3, 0, 1, 1), // cubic-bezier(0.3, 0, 1, 1)
  standard: Easing.bezier(0.4, 0, 0.2, 1), // crossfades and colour changes
} as const;

/** The only spring: press feedback, critically damped so it never overshoots. */
export const SPRING_PRESS = { damping: 28, stiffness: 420, mass: 1 } as const;

/** How far a pressed button shrinks. Never below 0.97. */
export const PRESS_SCALE = 0.98;

/** Skeleton breathing: opacity 1 to SKELETON_DIM and back, one half-cycle per SKELETON_HALF_CYCLE ms. */
export const SKELETON_DIM = 0.55;
export const SKELETON_HALF_CYCLE = 900;

/** Wait this long before showing a skeleton (fast loads never flash one), then keep it at least SKELETON_MIN_SHOWN. */
export const SKELETON_DELAY = 200;
export const SKELETON_MIN_SHOWN = 400;
