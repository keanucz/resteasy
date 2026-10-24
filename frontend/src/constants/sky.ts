import type { Scheme } from './theme';
import type { PillowState } from './status';

/**
 * The home screen's sky, as tuned in the moodboard. The sky carries the state; its bottom edge
 * follows `edge` and fades into the app, where the stats start.
 */
export const SKY = {
  /** Shape of the bottom edge for x in [-1, 1]; its highest value rises furthest: -cosh(1.5x). */
  edge: (x: number) => -Math.cosh(1.5 * x),
  /** px from the top to the lowest point of the edge. */
  horizon: 230,
  /** How far the edge rises, as a fraction of the horizon. */
  archHeight: 0.15,
  /** px below the edge over which the sky fades out (smoothstep). */
  fadeLength: 52,
  stars: true,
} as const;

type SkyLook = {
  /** Gradient [top, bottom]. */
  sky: [string, string];
  /** Colour of the headline's key word on this sky (at least 4.5:1). */
  ink: string;
  /** Optional glow: centre x as a fraction of width, radius as a fraction of width, colour, opacity. */
  glow?: { x: number; r: number; color: string; opacity: number };
};

export const SKY_LOOKS: Record<PillowState, Record<Scheme, SkyLook>> = {
  asleep: {
    dark: { sky: ['#121C48', '#284A8E'], ink: '#B9C8FF' },
    light: { sky: ['#C6DEFA', '#DCE8FB'], ink: '#2F55C8' },
  },
  restless: {
    dark: { sky: ['#26133D', '#6A2D6C'], ink: '#E2A8F5', glow: { x: 0.88, r: 0.5, color: '#E2A8F5', opacity: 0.4 } },
    light: { sky: ['#EEDDF3', '#F4C6DC'], ink: '#8E3BB3', glow: { x: 0.88, r: 0.5, color: '#F0D2FA', opacity: 0.4 } },
  },
  up: {
    dark: { sky: ['#1F2150', '#3D3570'], ink: '#FFD58A', glow: { x: 0.1, r: 0.8, color: '#F4C46C', opacity: 0.75 } },
    light: { sky: ['#DCE8F5', '#FCDBA2'], ink: '#A85C00', glow: { x: 0.1, r: 0.8, color: '#FAE2B6', opacity: 0.75 } },
  },
  alert: {
    dark: { sky: ['#2C0F1E', '#6E1E2C'], ink: '#FF9C94', glow: { x: 0.5, r: 0.75, color: '#E64C6B', opacity: 0.7 } },
    light: { sky: ['#FBE4E1', '#F6B6AC'], ink: '#C8202F', glow: { x: 0.5, r: 0.75, color: '#F3A6B5', opacity: 0.7 } },
  },
  offline: {
    dark: { sky: ['#24252E', '#3A3C46'], ink: '#B8BAC6' },
    light: { sky: ['#E4E5EA', '#EEEEF1'], ink: '#5C6178' },
  },
};

/** The detail line under the headline, solid for steady contrast on any sky. */
export const SKY_DETAIL: Record<Scheme, string> = { dark: '#E6E6F2', light: '#3B3B52' };

/** Photo ring: a neutral hairline, red only when she needs you. */
export const RING = {
  neutral: { dark: 'rgba(255, 255, 255, 0.28)', light: 'rgba(20, 20, 40, 0.18)' },
  alert: { dark: '#FF6B63', light: '#C93338' },
} as const;

/** Stars only while she is in bed; once she is up or needs you, the night is interrupted. */
export const STARRY_STATES: readonly PillowState[] = ['asleep', 'restless'];
