/** Design tokens. Every colour, spacing and font size in the app comes from here. */

export const colors = {
  background: '#FFFFFF',
  text: '#11181C',
  muted: '#687076',
  primary: '#0A7EA4',
} as const;

export const spacing = {
  xs: 4,
  sm: 8,
  md: 16,
  lg: 24,
  xl: 32,
} as const;

export const fontSizes = {
  body: 16,
  subtitle: 20,
  title: 32,
} as const;
