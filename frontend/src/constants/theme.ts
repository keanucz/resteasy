/**
 * Design tokens for code that cannot take a className (Switch colours, StatusBar, navigation, SVG).
 * Everything else should use Tailwind classes, which are built from the same palette.
 */

import { logo, modes, raw, states } from './palette';

export type Scheme = keyof typeof modes;
export type ThemeColors = (typeof modes)[Scheme];

export const palette = raw;
export const themes = modes;
export const stateColors = states;
export const logoColors = logo;

export const spacing = {
  xs: 4,
  sm: 8,
  md: 16,
  lg: 24,
  xl: 32,
} as const;

/** Mirrors borderRadius in tailwind.config.js: md is rounded-field, lg is rounded-card. */
export const radii = {
  sm: 8,
  md: 14,
  lg: 20,
  pill: 999,
} as const;

export const fontSizes = {
  body: 16,
  subtitle: 20,
  title: 32,
} as const;

/** Families for SVG text and other places that need a raw font name. */
export const fonts = {
  display: 'Literata_600SemiBold',
  displayItalic: 'Literata_600SemiBold_Italic',
  sans: 'Figtree_400Regular',
  sansSemibold: 'Figtree_600SemiBold',
} as const;
