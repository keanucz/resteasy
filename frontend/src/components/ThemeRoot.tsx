import { vars } from 'nativewind';
import type { PropsWithChildren } from 'react';
import { View } from 'react-native';

import { type Scheme, themes } from '@/constants/theme';
import { useTheme } from '@/hooks/useTheme';

/** "#2A2752" to "42 39 82", the form Tailwind's `rgb(var(--x) / <alpha-value>)` colours expect. */
function toChannels(hex: string): string {
  const n = parseInt(hex.slice(1), 16);
  return `${(n >> 16) & 255} ${(n >> 8) & 255} ${n & 255}`;
}

const SCHEME_VARS = Object.fromEntries(
  (Object.keys(themes) as Scheme[]).map((scheme) => [
    scheme,
    vars(Object.fromEntries(Object.entries(themes[scheme]).map(([role, hex]) => [`--${role}`, toChannels(hex)]))),
  ]),
) as Record<Scheme, ReturnType<typeof vars>>;

/** Sets the theme-role CSS variables (bg-canvas, text-ink, ...) for the current colour scheme. Wrap the app once. */
export function ThemeRoot({ children }: PropsWithChildren) {
  const { scheme } = useTheme();
  return <View style={[{ flex: 1 }, SCHEME_VARS[scheme]]}>{children}</View>;
}
