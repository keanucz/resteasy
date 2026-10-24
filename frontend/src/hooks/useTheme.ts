import { useColorScheme } from 'nativewind';

import { type Scheme, type ThemeColors, themes } from '@/constants/theme';

/** The active colour scheme and its colours. Falls back to dark, because the app is night-first. */
export function useTheme(): { scheme: Scheme; colors: ThemeColors } {
  const { colorScheme } = useColorScheme();
  const scheme: Scheme = colorScheme === 'light' ? 'light' : 'dark';
  return { scheme, colors: themes[scheme] };
}
